"""Run the Neo4j baseline comparison in five isolated repeats and retain raw logs.

Requires a running populated Neo4j deployment, a valid judge credential and the
declared dependencies. This runner does not pretend a snapshot test is Neo4j.
"""
import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src/evaluation"))
from revision_statistics import summarize


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--repeats",type=int,default=5)
    parser.add_argument("--limit",type=int,default=0)
    parser.add_argument("--methods",default="bm25,vector,kg")
    parser.add_argument("--kg-url",default="http://127.0.0.1:8000/api/ask")
    parser.add_argument("--no-judge",action="store_true")
    args=parser.parse_args()
    if args.repeats<1: parser.error("repeats must be positive")
    args.output.mkdir(parents=True,exist_ok=True)
    manifest={"repeats":args.repeats,"methods":args.methods,"limit":args.limit,
              "corpus":str(args.corpus.resolve()),"kg_url":args.kg_url,
              "platform":platform.platform(),"python":sys.version,
              "judge_status":"Gemini single-model proxy rubric; not a RAGAS package run or independent human evaluation",
              "protocol_status":"legacy native pipelines; snapshot controlled ablations are separate"}
    mp=args.output/"manifest.json"
    if mp.exists() and json.loads(mp.read_text())!=manifest:
        raise ValueError("Use a new output directory when configuration changes")
    mp.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    combined=[]
    for repeat in range(1,args.repeats+1):
        directory=args.output/f"repeat_{repeat}"
        env={**os.environ,"CORPUS_JSON_DIR":str(args.corpus.resolve()),"BENCHMARK_OUTPUT_DIR":str(directory.resolve())}
        cmd=[sys.executable,str(ROOT/"src/evaluation/run_baseline_comparison.py"),
             "--resume","--methods",args.methods,"--kg-url",args.kg_url,
             "--limit",str(args.limit),"--seed",str(20261111+repeat)]
        if args.no_judge: cmd.append("--no-judge")
        subprocess.run(cmd,env=env,cwd=ROOT,check=True)
        rows={}
        for line in (directory/"comparison_results.jsonl").read_text(encoding="utf-8").split("\n"):
            row=json.loads(line);row["repeat"]=repeat
            rows[(row["method"],row["question_id"])]=row
        combined.extend(rows.values())
    (args.output/"combined.jsonl").write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in combined),encoding="utf-8")
    stats=summarize(combined,reference="Proposed KG-RAG")
    (args.output/"statistics.json").write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding="utf-8")


if __name__=="__main__": main()
