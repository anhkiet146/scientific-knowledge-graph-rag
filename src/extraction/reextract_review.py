"""Re-extract scholarly articles with source quotes, validation and safe resume.

One whole-paper request per document before retries. Existing source data are
read only; accepted extraction, raw responses and rejected records are separate.
"""
from __future__ import annotations
import argparse
import collections
import datetime
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

try:
    from .ontology_profiles import ENTITY_TYPES,signatures
except ImportError:
    from ontology_profiles import ENTITY_TYPES,signatures
SIGNATURES=signatures()
try:
    from .prompt_library import (PROMPT_VERSION,SYSTEM_INSTRUCTION,USER_PREFIX,TEXT,
        prompt_hashes,build_user_prompt,repair_prompt)
except ImportError:
    from prompt_library import (PROMPT_VERSION,SYSTEM_INSTRUCTION,USER_PREFIX,TEXT,
        prompt_hashes,build_user_prompt,repair_prompt)
try:
    from .semantic_triage import audit as semantic_triage
except ImportError:
    from semantic_triage import audit as semantic_triage
try:
    from .source_quality import split_page, quality_report
except ImportError:
    from source_quality import split_page, quality_report
try:
    from .workflow_io import loads as strict_json_loads
except ImportError:
    from workflow_io import loads as strict_json_loads
PROMPT=USER_PREFIX


def schema():
    evidence={"type":"ARRAY","items":{"type":"OBJECT",
        "properties":{"section_id":{"type":"STRING"},"text":{"type":"STRING"}},
        "required":["section_id","text"]}}
    entity={"type":"OBJECT","properties":{"id":{"type":"STRING"},
        "type":{"type":"STRING","enum":ENTITY_TYPES},"description":{"type":"STRING"},
        "evidence":evidence},"required":["id","type","description","evidence"]}
    relation={"type":"OBJECT","properties":{"source":{"type":"STRING"},"target":{"type":"STRING"},
        "type":{"type":"STRING","enum":list(SIGNATURES)},"evidence":evidence},
        "required":["source","target","type","evidence"]}
    return {"type":"OBJECT","properties":{"entities":{"type":"ARRAY","items":entity},
        "relations":{"type":"ARRAY","items":relation}},"required":["entities","relations"]}


def normalize(text):
    return " ".join(unicodedata.normalize("NFKC",str(text)).split())


def sections_from_document(document):
    if not isinstance(document,dict):raise ValueError("Document must be an object")
    for field in ("title","paper_title","raw_header","abstract"):
        if document.get(field) is not None and not isinstance(document[field],str):raise ValueError("Invalid document text field: "+field)
    for field in ("authors","affiliations","sections"):
        values=document.get(field)
        if values is not None and (not isinstance(values,list) or any(not isinstance(item,dict) for item in values)):
            raise ValueError("Invalid document record array: "+field)
    for field,names in (("authors",("full_name",)),("affiliations",("name","institution"))):
        for item in (document.get(field) or []):
            if any(item.get(name) is not None and not isinstance(item[name],str) for name in names):raise ValueError("Invalid header metadata")
    sections=[]
    def add(title,text,kind="body",metadata=None):
        if isinstance(text,str) and text.strip():
            sections.append({"section_id":f"s{len(sections):03d}","title":title,"kind":kind,"text":text if kind=="pdf_page" else " ".join(text.split()),**(metadata or {})})
    add("Title",document.get("title",document.get("paper_title","")),"title")
    add("Authors and affiliations header",document.get("raw_header",""),"header")
    if not document.get("raw_header"):
        header="\n".join((a.get("full_name") or "") for a in (document.get("authors") or []))
        header+="\n"+"\n".join((a.get("name") or a.get("institution") or "") for a in (document.get("affiliations") or []))
        add("Authors and affiliations metadata",header,"header")
    add("Abstract",document.get("abstract",""),"abstract")
    for section in (document.get("sections") or []):
        if section.get("content") is not None and not isinstance(section["content"],str):raise ValueError("Section content must be text")
        paragraphs=section.get("paragraphs")
        if paragraphs is not None and (not isinstance(paragraphs,list) or any(not isinstance(p,dict) or not isinstance(p.get("text",""),str) for p in paragraphs)):
            raise ValueError("Invalid section paragraphs")
        if str(section.get("category","")).casefold() in {"references","acknowledgements","acknowledgments"}:continue
        text=section.get("content") or "\n".join(p.get("text","") for p in (section.get("paragraphs") or []))
        title=section.get("section_title",section.get("title",section.get("category","Section")))
        if section.get("category")=="pdf_page":
            fragments,rejected=split_page(text)
            for index,fragment in enumerate(fragments,1):
                metadata={"page":section.get("page"),"first_line":fragment["first_line"],"last_line":fragment["last_line"]}
                if rejected:
                    metadata["source_quality"]={"status":"partial_page_corrupt_lines_excluded","excluded_line_numbers":[r["line_number"] for r in rejected],"fragment":index,"fragments":len(fragments)}
                add(title if not rejected else f"{title} — clean fragment {index}/{len(fragments)}",fragment["text"],"pdf_page",metadata)
        else:
            add(title,text,"body",{"category":section.get("category","body")})
    return sections


def validate_extraction(payload,sections,*,require_names=False,ontology_profile='legacy-v3.1'):
    """Structural/quote validation, never a certificate of semantic accuracy."""
    if not isinstance(payload,dict) or any(not isinstance(payload.get(k),list) for k in ("entities","relations")):
        raise ValueError("Response must contain entity and relation arrays")
    relation_signatures=signatures(ontology_profile)
    source={};raw_source={};header_ids=set()
    for section in sections:
        if not isinstance(section,dict) or not isinstance(section.get("section_id"),str) or not isinstance(section.get("text"),str):
            raise ValueError("Invalid source section")
        sid=section["section_id"]
        if sid in source:raise ValueError("Duplicate source section ID")
        raw_source[sid]=section["text"];source[sid]=normalize(section["text"])
        if section.get("kind")=="header":header_ids.add(sid)
    issues=[]
    def evidence_for(item):
        records=item.get("evidence",[])
        if not isinstance(records,list) or len(records)>16:return []
        valid=[]
        for record in records:
            if not isinstance(record,dict):continue
            sid=record.get("section_id");quote=record.get("text")
            if not isinstance(sid,str) or sid not in source or not isinstance(quote,str):continue
            if "\ufffd" in quote or len(normalize(quote))<8 or normalize(quote) not in source[sid]:continue
            evidence={"section_id":sid,"text":quote}
            if "start" in record or "end" in record:
                start,end=record.get("start"),record.get("end")
                if type(start) is not int or type(end) is not int or not 0<=start<end<=len(raw_source[sid]):continue
                if raw_source[sid][start:end]!=quote:continue
                evidence.update(start=start,end=end)
            if "evidence_id" in record:
                if not isinstance(record["evidence_id"],str):continue
                evidence["evidence_id"]=record["evidence_id"]
            if evidence not in valid:valid.append(evidence)
        return valid
    entities=[];seen=set()
    for item in payload["entities"]:
        if not isinstance(item,dict):issues.append({"kind":"entity","reason":"not_object","item":item});continue
        identifier,typ=item.get("id"),item.get("type");evidence=evidence_for(item)
        name=item.get("name",identifier)
        reason=None
        if not isinstance(identifier,str) or not identifier.strip() or len(identifier)>2048 or not isinstance(typ,str) or typ not in ENTITY_TYPES:reason="invalid_id_or_type"
        elif require_names and "name" not in item:reason="missing_source_name"
        elif not isinstance(name,str) or not name.strip() or len(name)>2048:reason="invalid_source_name"
        elif not isinstance(item.get("description",""),str):reason="invalid_description"
        elif isinstance(item.get('evidence'),list) and len(item['evidence'])>16:reason="evidence_limit_exceeded"
        elif not evidence:reason="no_grounded_source_quote"
        elif typ in {"Author","Institution"} and not any(e["section_id"] in header_ids and normalize(name).casefold() in normalize(e["text"]).casefold() for e in evidence):reason="name_not_grounded_in_header"
        elif (normalize(identifier),typ) in seen:reason="duplicate_entity"
        if reason:issues.append({"kind":"entity","reason":reason,"item":item});continue
        if typ in {"Author","Institution"}:evidence=[e for e in evidence if e["section_id"] in header_ids and normalize(name).casefold() in normalize(e["text"]).casefold()]
        seen.add((normalize(identifier),typ))
        record={"id":identifier,"type":typ,"description":item.get("description",""),"evidence":evidence}
        if "name" in item:record["name"]=name
        if "measurement" in item:record["measurement"]=item["measurement"]
        entities.append(record)
    types=collections.defaultdict(set)
    for entity in entities:types[entity["id"]].add(entity["type"])
    relations=[];seen_relations=set()
    for item in payload["relations"]:
        if not isinstance(item,dict):issues.append({"kind":"relation","reason":"not_object","item":item});continue
        src,tgt,typ=item.get("source"),item.get("target"),item.get("type");evidence=evidence_for(item);reason=None
        if not isinstance(typ,str) or typ not in relation_signatures:reason="invalid_relation_type"
        elif not isinstance(src,str) or not isinstance(tgt,str):reason="invalid_endpoint_id"
        elif len(types.get(src,set()))!=1 or len(types.get(tgt,set()))!=1:reason="missing_or_ambiguous_endpoint"
        elif (next(iter(types[src])),next(iter(types[tgt])))!=relation_signatures[typ]:reason="invalid_type_signature"
        elif typ=='HAS_COMPONENT' and src==tgt:reason='self_component_relation'
        elif (src,typ,tgt) in seen_relations:reason="duplicate_relation"
        if typ=="AFFILIATED_WITH":evidence=[e for e in evidence if e["section_id"] in header_ids]
        if not reason and isinstance(item.get('evidence'),list) and len(item['evidence'])>16:reason="evidence_limit_exceeded"
        if not reason and not evidence:reason="no_grounded_source_quote"
        if reason:issues.append({"kind":"relation","reason":reason,"item":item});continue
        seen_relations.add((src,typ,tgt));relations.append({"source":src,"type":typ,"target":tgt,"evidence":evidence})
    return {"entities":entities,"relations":relations},issues


class APIBlocked(RuntimeError):
    def __init__(self,status,detail):super().__init__(status);self.status=status;self.detail=detail


class Client:
    def __init__(self,key,model,rpm,*,response_schema=None,system_instruction=None):
        if not isinstance(key,str) or not key.strip() or key!=key.strip():raise ValueError("Valid API key required")
        if not isinstance(rpm,(int,float)) or isinstance(rpm,bool) or not 0<rpm<float("inf"):raise ValueError("Finite positive request rate required")
        self.key=key;self.model=model;self.interval=60/rpm;self.last=0
        self.response_schema=response_schema if response_schema is not None else schema()
        self.system_instruction=system_instruction if system_instruction is not None else SYSTEM_INSTRUCTION
    def generate(self,prompt):
        pause=self.interval-(time.perf_counter()-self.last)
        if pause>0:time.sleep(pause)
        self.last=time.perf_counter();started=time.perf_counter()
        body={"systemInstruction":{"parts":[{"text":self.system_instruction}]},"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{
            "temperature":0,"maxOutputTokens":16384,"thinkingConfig":{"thinkingBudget":0},
            "responseMimeType":"application/json","responseSchema":self.response_schema}}
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        request=urllib.request.Request(url,data=json.dumps(body).encode(),
            headers={"Content-Type":"application/json","x-goog-api-key":self.key})
        try:
            with urllib.request.urlopen(request,timeout=180) as response:
                raw_bytes=response.read(16*1024*1024+1)
                if len(raw_bytes)>16*1024*1024:raise ValueError("API response exceeds limit")
                data=strict_json_loads(raw_bytes)
                if not isinstance(data,dict):raise ValueError("Invalid API response envelope")
        except urllib.error.HTTPError as exc:
            raw=exc.read().decode("utf-8",errors="replace").replace(self.key,"[REDACTED]")
            try:detail=json.loads(raw)
            except ValueError:detail={"message":raw[:1500]}
            if exc.code==429:
                daily="GenerateRequestsPerDay" in raw or "per day limit" in raw
                raise APIBlocked("daily_quota_exhausted" if daily else "rate_limit",detail) from None
            if exc.code in (400,401,403):raise APIBlocked(f"request_rejected_http_{exc.code}",detail) from None
            raise RuntimeError(f"Gemini HTTP {exc.code}") from None
        candidates=data.get("candidates",[])
        if not isinstance(candidates,list) or any(not isinstance(c,dict) for c in candidates):raise ValueError("Invalid API candidates")
        candidate=(candidates or [{}])[0]
        content=candidate.get("content") or {}
        if not isinstance(content,dict) or not isinstance(content.get("parts",[]),list):raise ValueError("Invalid API content")
        parts=content.get("parts",[])
        if any(not isinstance(p,dict) or not isinstance(p.get("text",""),str) for p in parts):raise ValueError("Invalid API text part")
        text="".join(p.get("text","") for p in parts if not p.get("thought"))
        return text,data,{"api_seconds":time.perf_counter()-started,"throttle_wait_s":max(0,pause),
            "model_version":data.get("modelVersion"),"finish_reason":candidate.get("finishReason"),
            "usage":data.get("usageMetadata",{}),"request_prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest()}


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path,data):
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    temporary.replace(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--keys-file",type=Path)
    parser.add_argument("--model",default="gemini-2.5-flash",choices=["gemini-2.5-flash"])
    parser.add_argument("--requests-per-minute",type=float,default=4)
    parser.add_argument("--limit",type=int,default=0)
    parser.add_argument("--start-at",type=int,default=1,help="One-based source order for a pilot; not a new extraction method")
    parser.add_argument("--preflight",action="store_true")
    parser.add_argument("--legacy-quote-transport",action="store_true",help="Explicit legacy reproduction only; new work uses strict_runner.py")
    args=parser.parse_args()
    if not args.preflight and not args.legacy_quote_transport:
        parser.error("Legacy quote runner is disabled by default; use scripts/extract_entities.py (strict v3)")
    if not 0<args.requests_per_minute<float("inf"):parser.error("Finite positive requests-per-minute required")
    files=sorted(p for p in args.input.glob("*.json") if not p.name.startswith("_"))
    if not files:raise ValueError("No source documents")
    if not 1<=args.start_at<=len(files):parser.error("start-at is outside the source corpus")
    args.output.mkdir(parents=True,exist_ok=True)
    manifest={"protocol":"whole-paper-extraction-review-v2.3","prompt_version":PROMPT_VERSION,"source_text_preprocessing":"preserve PDF page layout text; collapse whitespace in other sections; original JSON snapshot retained","model":args.model,"temperature":0,
        "max_output_tokens":16384,"thinking_budget":0,"requests_per_minute":args.requests_per_minute,
        "prompt_sha256":hashlib.sha256((SYSTEM_INSTRUCTION+"\n"+PROMPT).encode()).hexdigest(),"prompt_file_sha256":prompt_hashes(),"schema":schema(),
        "source_quality_sha256":digest(Path(__file__).with_name("source_quality.py")),"source_quality_policy":"split PDF pages at U+FFFD-bearing lines; exclude corrupt lines from evidence; originals retained","semantic_triage_sha256":digest(Path(__file__).with_name("semantic_triage.py")),"code_sha256":digest(Path(__file__)),"prompt_library_sha256":digest(Path(__file__).with_name("prompt_library.py")),"entity_types":ENTITY_TYPES,"relation_signatures":SIGNATURES,
        "n_documents":len(files),"sources":[{"file":p.name,"sha256":digest(p)} for p in files],
        "validation_limit":"Quote existence and typed endpoints are checked; semantic entailment and extraction accuracy still require independent review."}
    mp=args.output/"manifest.json"
    if mp.exists():
        # JSON stores signature tuples as lists; compare canonical serialization.
        if json.loads(mp.read_text(encoding="utf-8"))!=json.loads(json.dumps(manifest)):
            raise ValueError("Input/prompt/model/code changed; choose a new output directory")
    else:write_json(mp,manifest)
    for folder in ("source_snapshot","extracted","raw_responses","validation","completion","requests","prompt_snapshot","source_quality"):(args.output/folder).mkdir(exist_ok=True)
    (args.output/"prompt.txt").write_text(PROMPT,encoding="utf-8")
    (args.output/"system_prompt.txt").write_text(SYSTEM_INSTRUCTION,encoding="utf-8")
    for name,text in TEXT.items():(args.output/"prompt_snapshot"/name).write_text(text,encoding="utf-8")
    (args.output/"runner.py").write_bytes(Path(__file__).read_bytes())
    for p in files:
        saved=args.output/"source_snapshot"/p.name
        if not saved.exists():saved.write_bytes(p.read_bytes())
        if digest(saved)!=digest(p):raise ValueError("Source snapshot changed")
    print(f"Verified {len(files)} source documents; model={args.model}",flush=True)
    if args.preflight:return
    key=os.getenv("GEMINI_API_KEY","")
    if args.keys_file:
        keys=json.loads(args.keys_file.read_text(encoding="utf-8-sig"))
        key=keys.get("api_key") or keys.get("keys",{}).get(keys.get("active",""),"")
    if not key:raise ValueError("Set GEMINI_API_KEY or --keys-file")
    source_hashes={record["file"]:record["sha256"] for record in manifest["sources"]}
    client=Client(key,args.model,args.requests_per_minute)
    completed=0;failed=0;blocked=None
    targets=files[args.start_at-1:]
    targets=targets[:args.limit] if args.limit else targets
    def progress(state):
        write_json(args.output/"progress.json",{"state":state,"model":args.model,"target_documents":len(files),
            "completed_documents":len(list((args.output/"completion").glob("*.json"))),
            "failed_this_invocation":failed,"last_updated_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "blocked":blocked})
    progress("running")
    for index,path in enumerate(targets,1):
        if (args.output/"STOP").exists():
            progress("stopped_by_request")
            print("Stopped at a document boundary; progress saved",flush=True)
            return 0
        destination=args.output/"extracted"/path.name;receipt=args.output/"completion"/path.name
        if receipt.exists() and destination.exists():
            saved=json.loads(receipt.read_text(encoding="utf-8"))
            if saved.get("output_sha256")==digest(destination):completed+=1;continue
            raise ValueError("Completed extraction was modified: "+path.name)
        snapshot=args.output/"source_snapshot"/path.name
        if digest(snapshot)!=source_hashes[path.name]:raise ValueError("Frozen source changed")
        document=json.loads(snapshot.read_text(encoding="utf-8-sig"))
        sections=sections_from_document(document)
        quality=quality_report(document)
        write_json(args.output/"source_quality"/path.name,quality)
        prompt=build_user_prompt(sections)
        success=False;previous_candidate="";failure=""
        for attempt in range(1,3):
            metadata={}
            try:
                active_prompt=prompt if attempt==1 else repair_prompt(prompt,previous_candidate,failure)
                write_json(args.output/"requests"/(path.stem+f".attempt{attempt}.json"),
                    {"system_instruction":SYSTEM_INSTRUCTION,"user_prompt":active_prompt})
                text,raw,metadata=client.generate(active_prompt)
                previous_candidate=text
                write_json(args.output/"raw_responses"/(path.stem+f".attempt{attempt}.json"),raw)
                if metadata["finish_reason"]!="STOP":raise ValueError("Incomplete response: "+str(metadata["finish_reason"]))
                payload=json.loads(text)
                accepted,issues=validate_extraction(payload,sections)
                semantic_review=semantic_triage(accepted)
                write_json(args.output/"validation"/path.name,{"issues":issues,"accepted_entities":len(accepted["entities"]),
                    "accepted_relations":len(accepted["relations"]),"metadata":metadata,"semantic_review":semantic_review})
                if not accepted["entities"]:raise ValueError("No grounded entities; not recorded as a completed extraction")
                result={"filename":path.name,"paper_title":document.get("title",document.get("paper_title","")),
                    "extraction_result":accepted,"extraction_metadata":metadata,"semantic_review":semantic_review,"source_quality":quality,
                    "source_sha256":source_hashes[path.name],"prompt_sha256":manifest["prompt_sha256"]}
                write_json(destination,result)
                write_json(receipt,{"file":path.name,"source_sha256":source_hashes[path.name],"output_sha256":digest(destination),
                    "entities":len(accepted["entities"]),"relations":len(accepted["relations"]),
                    "rejected_records":len(issues),"metadata":metadata})
                completed+=1;success=True;progress("running")
                print(f"[{index}/{len(targets)}] {path.name}: {len(accepted['entities'])} entities, {len(accepted['relations'])} relations, {len(issues)} rejected",flush=True)
                break
            except APIBlocked as exc:
                blocked={"status":exc.status,"file":path.name,"detail":exc.detail};progress("blocked")
                print("STOPPED: "+exc.status+"; progress saved",flush=True)
                return 3
            except Exception as exc:
                failure=type(exc).__name__+": "+str(exc)
                error={"file":path.name,"attempt":attempt,"error":type(exc).__name__+": "+str(exc).replace(key,"[REDACTED]"),"metadata":metadata}
                with (args.output/"failures.jsonl").open("a",encoding="utf-8") as f:f.write(json.dumps(error,ensure_ascii=False)+"\n")
                print(f"  attempt {attempt} failed: {type(exc).__name__}",flush=True)
        if not success:failed+=1;progress("running")
    progress("complete" if len(list((args.output/"completion").glob("*.json")))==len(files) else "partial")
    return 0 if not failed else 2


if __name__=="__main__":raise SystemExit(main())
