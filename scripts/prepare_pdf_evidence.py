"""Preserve PDF page text alongside parsed metadata; never infer table cells."""
import argparse, hashlib, json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src/extraction"))
from pdf_source import attach_pdf_pages

def prepare(source,pdf,destination):
    document=json.loads(source.read_text(encoding="utf-8-sig"))
    document=attach_pdf_pages(document,pdf)
    destination.write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding="utf-8")
    return {"file":source.name,**document["pdf_evidence"],"status":"needs_ocr" if document["pdf_evidence"]["empty_pages"] else "text_prepared_not_semantically_verified"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args=parser.parse_args()
    if args.output.resolve() in {args.input.resolve(), args.pdf.resolve()}: raise ValueError("Use a separate output directory")
    args.output.mkdir(parents=True, exist_ok=True)
    records=[]
    for source in sorted(args.input.glob("*.json")):
        if source.name.startswith("_"): continue
        pdf=args.pdf/(source.stem+".pdf")
        if not pdf.exists():
            records.append({"file": source.name, "status": "missing_pdf"}); continue
        try: records.append(prepare(source,pdf,args.output/source.name))
        except Exception as exc: records.append({"file":source.name,"status":"parse_failed","error":str(exc)})
    (args.output/"_pdf_preparation_manifest.json").write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
    from collections import Counter
    print(dict(Counter(r["status"] for r in records)))

if __name__ == "__main__": main()
