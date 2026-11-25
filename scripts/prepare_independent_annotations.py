"""Prepare blind blank extraction tasks from an existing frozen sample, not labels."""
import argparse,csv,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src/extraction"))
from reextract_review import sections_from_document

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample",type=Path,required=True);parser.add_argument("--corpus",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    with args.sample.open(encoding="utf-8-sig",newline="") as stream: rows=list(csv.DictReader(stream))
    tasks=[]
    for row in rows:
        source=args.corpus/(Path(row["filename"]).stem+".json")
        document=json.loads(source.read_text(encoding="utf-8"))
        tasks.append({"protocol_id":"strict-extraction-v3.0","paper_id":row["paper_id"],"filename":row["filename"],"source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),"sections":sections_from_document(document),"entities":[],"relations":[],"annotation_status":"pending","notes":""})
    args.output.mkdir(parents=True,exist_ok=True)
    for label in ["A","B"]:
        (args.output/f"annotator_{label}_tasks.jsonl").write_text("".join(json.dumps(t,ensure_ascii=False)+"\n" for t in tasks),encoding="utf-8")
    (args.output/"manifest.json").write_text(json.dumps({"n_tasks":len(tasks),"labels_completed":0,"sample_manifest_sha256":hashlib.sha256(args.sample.read_bytes()).hexdigest(),"tasks":[{k:t[k] for k in ["paper_id","filename","source_sha256"]} for t in tasks]},indent=2),encoding="utf-8")
    print(f"Prepared {len(tasks)} independent blank tasks per annotator; no annotation completed")

if __name__=="__main__":main()
