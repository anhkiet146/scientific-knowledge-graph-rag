"""Offline retrieval-only validation. No answer generation, judgment, or QA scores."""
import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
from prepare_review_dataset import verify, read_questions
from snapshot_benchmark import BM25Index, SnapshotGraph, load_chunks, generation_prompt
from hybrid_retrieval import build_query_plan, rerank_candidates


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset",type=Path,required=True)
    parser.add_argument("--translations",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    frozen=verify(args.dataset)
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("Choose a new empty output directory")
    args.output.mkdir(parents=True,exist_ok=True)
    translation_cache=json.loads(args.translations.read_text(encoding="utf-8"))
    qs=read_questions(args.dataset/"questions.py")
    chunks=load_chunks(args.dataset/"corpus")
    bm25=BM25Index([c["title"]+" "+c["text"] for c in chunks])
    graph=SnapshotGraph(args.dataset/"extracted")
    raw=SnapshotGraph(args.dataset/"extracted",normalize=False)
    variants={"bm25":{},"kg":{},"kg_no_expansion":{"hops":0},"kg_raw":{"raw":True},
              "kg_no_semantic":{"multipliers":{"semantic":0}},
              "kg_no_relation":{"multipliers":{"relation":0}},
              "kg_verified":{"note":"retrieval only; claim verification is NOT executed"}}
    report={"stage":"retrieval_only","n_questions":len(qs),"n_variants":len(variants),
        "n_source_chunks":len(chunks),"top_k":8,"context_char_budget":12000,
        "query_analysis":"historical cached English translation + current deterministic build_query_plan; no LLM call",
        "dataset_manifest_sha256":hashlib.sha256((args.dataset/"manifest.json").read_bytes()).hexdigest(),
        "translations_sha256":hashlib.sha256(args.translations.read_bytes()).hexdigest(),
        "n_failed":0,"n_empty_contexts":0,"n_successful_calls":0,"method_counts":{},
        "interpretation":"Execution diagnostics only. No generation, verification, QA quality, significance or end-to-end latency claims."}
    rows=[]
    with (args.output/"retrieval_records.jsonl").open("w",encoding="utf-8") as out:
        for qid,item in enumerate(qs,1):
            question=item["question"]
            translated=translation_cache.get(hashlib.sha1(question.encode()).hexdigest())
            if not isinstance(translated,str) or not translated.strip():
                raise ValueError(f"Missing cached translation for question {qid}; no silent untranslated fallback")
            plan=build_query_plan(question,{"keywords":[translated]})
            query=question+" "+translated
            for method,options in variants.items():
                record={"stage":"retrieval_only","question_id":qid,"method":method,"query_plan":plan,"error":None}
                start=time.perf_counter()
                try:
                    if method=="bm25": context=[chunks[i] for i,_ in bm25.search(query,8)]
                    else:
                        g=raw if options.get("raw") else graph
                        candidates=g.retrieve(query,hops=options.get("hops",2))
                        context=rerank_candidates(question,plan,candidates,max_context=8,
                                                  signal_multipliers=options.get("multipliers"))
                    bounded=[];size=0
                    for c in context:
                        length=len(json.dumps(c,ensure_ascii=False))
                        if size+length>12000:break
                        bounded.append(c);size+=length
                    if method=="kg_no_expansion" and any(c.get("connections") for c in bounded):
                        raise AssertionError("Graph neighbors leaked into no-expansion context")
                    prompt=generation_prompt(question,bounded)
                    record.update(retrieved_context=bounded,n_contexts=len(bounded),context_chars=size,
                                  generation_prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest())
                    assert len(bounded)<=8 and size<=12000
                    if not bounded:report["n_empty_contexts"]+=1
                    report["n_successful_calls"]+=1
                except Exception as exc:
                    record["error"]=type(exc).__name__+": "+str(exc)
                    report["n_failed"]+=1
                record["retrieval_seconds"]=time.perf_counter()-start
                if options.get("note"):record["note"]=options["note"]
                out.write(json.dumps(record,ensure_ascii=False)+"\n")
                rows.append({k:record.get(k) for k in ("question_id","method","n_contexts","context_chars","retrieval_seconds","error")})
                report["method_counts"][method]=report["method_counts"].get(method,0)+1
            print(f"retrieval preflight {qid}/{len(qs)}",flush=True)
    with (args.output/"retrieval_diagnostics.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (args.output/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False),flush=True)
    if report["n_failed"]:raise SystemExit(1)


if __name__=="__main__":main()
