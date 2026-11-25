"""Offline input integrity, development/holdout separation and advisory PDF triage."""
import argparse,collections,csv,hashlib,json,random,re
from pathlib import Path

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus",type=Path,required=True)
    parser.add_argument("--sample",type=Path,required=True)
    parser.add_argument("--historical-outputs",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    with args.sample.open(encoding="utf-8-sig",newline="") as stream:sample=list(csv.DictReader(stream))
    holdout={Path(r["filename"]).stem for r in sample}
    if len(holdout)!=40:raise ValueError("Expected 40 distinct holdout papers")
    exposures={}
    for run in sorted(args.historical_outputs.glob("reextraction*")):
        exposures[run.name]=sorted(p.stem for p in (run/"extracted").glob("*.json"))
    exposed=set(n for names in exposures.values() for n in names)
    overlap=sorted(exposed & holdout)
    if overlap:raise ValueError("Previously extracted development pilots overlap holdout: "+str(overlap))
    files=sorted(p for p in args.corpus.glob("*.json") if not p.name.startswith("_"))
    source_names={p.stem for p in files}
    if not holdout<=source_names:raise ValueError("Holdout papers missing from source")
    candidates=sorted(source_names-holdout-exposed)
    selected=sorted(random.Random(20261112).sample(candidates,10))
    integrity=[];flags=[];pages=0;table_pages=0
    for source in files:
        document=json.loads(source.read_text(encoding="utf-8"))
        pdf=document.get("pdf_evidence",{});pdf_path=Path(pdf.get("path",""))
        matched=pdf_path.is_file() and digest(pdf_path)==pdf.get("sha256")
        sections=document.get("sections",[]);page_sections=[s for s in sections if s.get("category")=="pdf_page"]
        entry={"file":source.name,"source_sha256":digest(source),"pdf_sha256":pdf.get("sha256"),"pdf_hash_matches":matched,
               "page_count":len(page_sections),"page_count_matches":len(page_sections)==pdf.get("pages")}
        integrity.append(entry);pages+=len(page_sections)
        if not matched or not entry["page_count_matches"]:flags.append({"file":source.name,"reason":"integrity_mismatch"})
        header=document.get("raw_header","")
        if not header and not document.get("authors"):flags.append({"file":source.name,"reason":"missing_author_header_metadata"})
        for section in page_sections:
            text=section.get("content","");reasons=[]
            if len(text.strip())<80:reasons.append("short_or_empty_page_needs_visual_check")
            if "\ufffd" in text:reasons.append("replacement_character_present")
            if re.search(r"\bTable\s*\d",text,re.I):table_pages+=1
            if reasons:flags.append({"file":source.name,"page":section.get("page"),"reasons":reasons})
    report={"documents":len(files),"pages":pages,"pages_with_table_mentions":table_pages,"integrity_failures":sum(not r["pdf_hash_matches"] or not r["page_count_matches"] for r in integrity),
            "holdout_papers":len(holdout),"previous_pilot_papers":len(exposed),"development_holdout_overlap":overlap,
            "additional_development_papers":len(selected),"advisory_flags":len(flags),
            "limitations":"Hash/page-count and lexical checks do not validate table-cell alignment or semantic extraction. Rotated text may be missing despite nonempty pages; visual review remains required."}
    split={"protocol_id":"review-protocol-v1","seed":20261112,"holdout":sorted(holdout),"historical_pilot_exposures":exposures,
           "development":sorted(exposed | set(selected)),"additional_development":selected,"selection":"seeded sample excluding holdout and all historical extraction pilots"}
    for name,value in [("input_integrity.json",integrity),("input_triage.json",flags),("split_manifest.json",split),("input_summary.json",report)]:
        (args.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=True))
    if report["integrity_failures"]:raise SystemExit(2)

if __name__=="__main__":main()
