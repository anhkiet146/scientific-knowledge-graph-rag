"""Freeze the source/extraction corpus for review experiments, with verifiable hashes."""
import argparse
import ast
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src/normalization"))
from normalize_entities import normalize_folder


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_questions(path):
    for node in ast.parse(path.read_text(encoding="utf-8-sig")).body:
        if isinstance(node,ast.Assign) and any(isinstance(x,ast.Name) and x.id=="data" for x in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError("No literal question data list")


def prepare(corpus,extracted,question_file,output):
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty output directory; frozen datasets are not overwritten")
    sources={p.name:p for p in corpus.glob("*.json") if not p.name.startswith("_")}
    extractions={p.name:p for p in extracted.glob("*.json") if not p.name.startswith("_")}
    if set(sources)!=set(extractions):
        raise ValueError("Corpus and extraction filenames differ; align documents before freezing")
    questions=read_questions(question_file)
    if len(sources)!=482 or len(questions)!=45:
        raise ValueError("This protocol requires exactly 482 documents and 45 questions")
    if len({q["question"].strip() for q in questions})!=len(questions):
        raise ValueError("Duplicate questions")
    output.mkdir(parents=True,exist_ok=True)
    for name,paths in (("corpus",sources),("extracted",extractions)):
        folder=output/name;folder.mkdir()
        for path in paths.values():
            json.loads(path.read_text(encoding="utf-8-sig"))
            shutil.copy2(path,folder/path.name)
    shutil.copy2(question_file,output/"questions.py")
    normalization=normalize_folder(output/"extracted",output/"normalized_exact")
    with (output/"qa_validation_checklist.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=["question_id","question","reference_answer","existing_review_status",
            "source_paper","source_page_or_section","annotator_a","annotator_b","adjudication","ready_for_scoring"])
        writer.writeheader()
        for i,q in enumerate(questions,1):
            writer.writerow(dict(question_id=i,question=q["question"],reference_answer=q.get("ground_truth",""),
                existing_review_status=q.get("review_status","pending_independent_validation"),ready_for_scoring="NO"))
    records=[]
    for folder in ("corpus","extracted","normalized_exact"):
        for path in sorted((output/folder).iterdir()):
            if path.is_file():records.append({"path":path.relative_to(output).as_posix(),"sha256":sha256(path),"bytes":path.stat().st_size})
    records.append({"path":"questions.py","sha256":sha256(output/"questions.py"),"bytes":(output/"questions.py").stat().st_size})
    manifest={"protocol":"review-corpus-482-v1","n_documents":len(sources),"n_questions":len(questions),
        "reference_status":"project-internal; independent checking/adjudication not completed",
        "first_reference_correction":"Tran Van Huu -> Tran Van Hau; DOI 10.22144/ctu.jen.2018.018 page 1",
        "normalization":{k:v for k,v in normalization.items() if k!="issues"},"files":records}
    (output/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    return manifest


def verify(output):
    manifest=json.loads((output/"manifest.json").read_text(encoding="utf-8"))
    root=output.resolve()
    for record in manifest["files"]:
        path=(root/record["path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file() or sha256(path)!=record["sha256"]:
            raise ValueError(f"Missing or modified frozen input: {record['path']}")
    for name in ("corpus","extracted","normalized_exact"):
        actual={p.relative_to(root).as_posix() for p in (root/name).iterdir() if p.is_file()}
        expected={r["path"] for r in manifest["files"] if r["path"].startswith(name+"/")}
        if actual!=expected:raise ValueError(f"Added/removed files in frozen {name}")
    return manifest


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus",type=Path)
    parser.add_argument("--extracted",type=Path)
    parser.add_argument("--questions",type=Path,default=ROOT/"data/qa_evaluation/qa_test_set.py")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--verify-only",action="store_true")
    args=parser.parse_args()
    if args.verify_only: result=verify(args.output)
    else:
        if not args.corpus or not args.extracted:parser.error("--corpus and --extracted are required")
        result=prepare(args.corpus,args.extracted,args.questions,args.output)
        verify(args.output)
    print(json.dumps({"verified":True,"documents":result["n_documents"],"questions":result["n_questions"],
                      "hashed_files":len(result["files"]),"normalization":result["normalization"]},ensure_ascii=False))
