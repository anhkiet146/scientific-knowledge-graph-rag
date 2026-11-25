"""Exact same-type normalization; semantic similarity never triggers an automatic merge."""
import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def normalize_surface(value):
    """Legacy punctuation-stripping key, retained for historical replay only."""
    value=unicodedata.normalize("NFKC",str(value)).casefold()
    return " ".join(re.sub(r"[^\w\s]"," ",value).split())


def source_surface(value):
    return " ".join(unicodedata.normalize("NFC", str(value)).split())


def normalization_key(typ, name, paper, strategy):
    if strategy == "source_preserving":
        return typ, paper if typ in {"Author", "Metric"} else "", source_surface(name)
    return typ, "", normalize_surface(name)

def extraction_payload(document):
    payload=document.get("extraction_result",document)
    if isinstance(payload,list):
        payload={"entities":[e for part in payload for e in part.get("entities",[])],
                 "relations":[r for part in payload for r in part.get("relations",[])]}
    if not isinstance(payload,dict): raise ValueError("Invalid extraction payload")
    return payload

def normalize_folder(input_dir,output_dir,strategy="exact"):
    if strategy not in {"exact", "identity", "source_preserving"}:
        raise ValueError("Unknown normalization strategy")
    if input_dir.resolve()==output_dir.resolve(): raise ValueError("Use a separate output directory")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("Use a new output directory; existing artifacts are not overwritten")
    documents=[];groups=defaultdict(Counter)
    for path in sorted(p for p in input_dir.glob("*.json") if not p.name.startswith("_")):
        d=json.loads(path.read_text(encoding="utf-8"));p=extraction_payload(d)
        documents.append((path,d,p))
        for e in p.get("entities",[]):
            name=(e.get("name") or e.get("id", "")) if strategy=="source_preserving" else e.get("id",e.get("name",""));typ=e.get("type","")
            if name and typ: groups[normalization_key(typ,name,path.name,strategy)][name]+=1
    canonical={key:sorted(names,key=lambda s:(-names[s],s))[0] for key,names in groups.items()}
    output_dir.mkdir(parents=True,exist_ok=True)
    issues=[];changed=0;raw_names=set()
    for path,d,p in documents:
        mapping=defaultdict(set)
        for e in p.get("entities",[]):
            name=(e.get("name") or e.get("id", "")) if strategy=="source_preserving" else e.get("id",e.get("name",""));typ=e.get("type","")
            if not name or not typ: continue
            identifier=e.get("id",name)
            raw_names.add((typ,name))
            target=canonical[normalization_key(typ,name,path.name,strategy)] if strategy!="identity" else name
            target_id=identifier if strategy=="source_preserving" else target
            mapping[identifier].add(target_id)
            if target!=name:
                e.setdefault("aliases",[])
                if name not in e["aliases"]: e["aliases"].append(name)
                if strategy=="source_preserving":e["name"]=target
                else:e["id"]=target
                changed+=1
            if strategy=="source_preserving":
                e["identity_scope"]="paper" if typ in {"Author","Metric"} else "corpus"
            e["normalization_provenance"]={"original_name":name,"strategy":strategy,"paper":path.name}
        for r in p.get("relations",[]):
            for field in ("source","target"):
                values=mapping.get(r.get(field),set())
                if len(values)==1: r[field]=next(iter(values))
                else: issues.append({"paper":path.name,"relation":r,"endpoint":field,"reason":"missing or ambiguous untyped endpoint"})
        if "extraction_result" in d: d["extraction_result"]=p
        (output_dir/path.name).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
    report={"papers":len(documents),"strategy":strategy,"unique_original_typed_names":len(raw_names),
            "canonical_typed_names":len(groups) if strategy!="identity" else len(raw_names),
            "changed_mentions":changed,"unresolved_relation_endpoints":len(issues),
            "key_policy":"NFC and whitespace only; Author/Metric scoped by paper" if strategy=="source_preserving" else "Legacy NFKC/casefold/punctuation stripping; not a correctness guarantee",
            "homonym_policy":"Paper scoping prevents automatic cross-paper Author/Metric merges; within-paper disambiguation remains unverified." if strategy=="source_preserving" else "Same name/type can still be homonymous across papers; provenance retained, human disambiguation required.",
            "issues":issues}
    (output_dir/"_normalization_audit.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    with (output_dir/"_normalization_review.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.writer(f);writer.writerow(["entity_type","paper_scope","normalized_surface","surface_forms","decision","notes"])
        for (typ,scope,surface),names in sorted(groups.items()):
            if len(names)>1: writer.writerow([typ,scope,surface,json.dumps(dict(names),ensure_ascii=False),"",""])
    return report

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,default=ROOT/"data/extracted_json")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--strategy",choices=["source_preserving","exact","identity"],default="source_preserving")
    args=parser.parse_args()
    report=normalize_folder(args.input,args.output,args.strategy)
    print(json.dumps({k:v for k,v in report.items() if k!="issues"},ensure_ascii=False))
