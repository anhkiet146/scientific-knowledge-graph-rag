"""Matched-query snapshot KG ablations with a pinned proxy token budget. No LLM calls."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src/extraction')]
from prepare_review_dataset import verify
from snapshot_benchmark import SnapshotGraph
from hybrid_retrieval import build_query_plan,rerank_candidates
from workflow_io import read_json,atomic_json,canonical_hash,file_hash
from context_budget import pack

VARIANTS={'kg':{},'kg_no_expansion':{'hops':0},'kg_raw':{'raw':True},
    'kg_no_semantic':{'multipliers':{'semantic':0}},'kg_no_relation':{'multipliers':{'relation':0}},
    'kg_verified':{'verification_executed':False}}


def run(dataset,vector,baseline_contexts,cache,output):
    if output.exists():raise ValueError('Fresh output required')
    verify(dataset)
    original=read_json(vector/'manifest.json')
    if original['dataset_manifest_sha256']!=file_hash(dataset/'manifest.json'):raise ValueError('Different frozen corpora')
    base_manifest=read_json(baseline_contexts/'tokenizer_manifest.json')
    base=[json.loads(s) for s in (baseline_contexts/'bounded_contexts.jsonl').read_text(encoding='utf-8').split('\n') if s]
    queries=[json.loads(s) for s in (vector/'retrieval_records.jsonl').read_text(encoding='utf-8').split('\n') if s]
    query_by_id={};baseline_keys=set()
    for row in queries:
        qid=row['question_id'];query=(row['question'],row['shared_query'])
        if qid in query_by_id and query_by_id[qid]!=query:raise ValueError('Different method queries')
        query_by_id[qid]=query
    if set(query_by_id)!=set(range(1,46)):raise ValueError('Incomplete 45-question input')
    os.environ['TIKTOKEN_CACHE_DIR']=str(cache.resolve())
    import tiktoken
    if importlib.metadata.version('tiktoken')!=base_manifest['version']:raise ValueError('Different tokenizer package')
    enc=tiktoken.get_encoding(base_manifest['encoding']);digest=hashlib.sha256()
    for token,rank in sorted(enc._mergeable_ranks.items(),key=lambda item:item[1]):
        digest.update(len(token).to_bytes(4,'big'));digest.update(token);digest.update(rank.to_bytes(4,'big'))
    digest.update(json.dumps(enc._special_tokens,sort_keys=True).encode())
    if digest.hexdigest()!=base_manifest['vocabulary_sha256']:raise ValueError('Different tokenizer vocabulary')
    def encode(text):return enc.encode(text,disallowed_special=())
    for row in base:
        key=(row['question_id'],row['method'])
        if key in baseline_keys:raise ValueError('Duplicate baseline context')
        baseline_keys.add(key)
        bounded,text,count=pack(row['context'],encode)
        if bounded!=row['context'] or text!=row['context_json'] or count!=row['context_tokens'] or canonical_hash(text)!=row['context_sha256']:
            raise ValueError('Baseline serialization or budget changed')
    if baseline_keys!={(q,m) for q in range(1,46) for m in ('bm25','vector')}:raise ValueError('Incomplete baseline contexts')
    start=time.perf_counter();graph=SnapshotGraph(dataset/'extracted');raw=SnapshotGraph(dataset/'extracted',normalize=False)
    setup=time.perf_counter()-start;rows=[]
    for qid,(question,shared_query) in sorted(query_by_id.items()):
        # Do not give KG untruncated original-language query information unavailable to the shared baseline input.
        plan=build_query_plan(shared_query,{'keywords':[shared_query]})
        for method,options in VARIANTS.items():
            start=time.perf_counter();g=raw if options.get('raw') else graph
            candidates=g.retrieve(shared_query,hops=options.get('hops',2))
            ranked=rerank_candidates(shared_query,plan,candidates,max_context=8,signal_multipliers=options.get('multipliers'))
            context,text,count=pack(ranked,encode)
            if method=='kg_no_expansion' and any(c.get('connections') or c.get('degree') or c.get('hop_distance') for c in ranked):
                raise ValueError('Graph expansion/degree leaked into no-expansion ablation')
            rows.append({'question_id':qid,'question':question,'shared_query':shared_query,'method':method,'query_plan':plan,
                'context':context,'context_json':text,'context_sha256':canonical_hash(text),'context_tokens':count,
                'candidate_count':len(candidates),'ranked_count':len(ranked),'retained_count':len(context),
                'prefix_exceeds_budget':bool(ranked) and not context,'retrieval_seconds':time.perf_counter()-start,
                'generation_status':'not_executed','verification_executed':False,'quality_score':None})
    for qid in query_by_id:
        lookup={r['method']:r for r in rows if r['question_id']==qid}
        if lookup['kg']['context_json']!=lookup['kg_verified']['context_json']:
            raise ValueError('Verification-only variant changed retrieval')
    verify(dataset)
    output.mkdir(parents=True)
    with (output/'kg_contexts.jsonl').open('w',encoding='utf-8') as stream:
        for row in rows:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    with (output/'all_eight_methods.jsonl').open('w',encoding='utf-8') as stream:
        for row in base+rows:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    atomic_json(output/'manifest.json',{'protocol_id':'kg-ablation-token-preflight-v1','dataset_manifest_sha256':file_hash(dataset/'manifest.json'),
        'baseline_context_file_sha256':file_hash(baseline_contexts/'bounded_contexts.jsonl'),'tokenizer':base_manifest,
        'code_sha256':{p.name:file_hash(p) for p in [Path(__file__),Path(__file__).with_name('context_budget.py'),
            Path(__file__).with_name('snapshot_benchmark.py'),ROOT/'src/retrieval/hybrid_retrieval.py',ROOT/'src/normalization/normalize_entities.py']},
        'variants':VARIANTS,'query_policy':'Identical baseline shared_query, deterministic KG query plan from that string only',
        'historical_graph_warning':'Frozen historical extraction, not approved v3.1 reextraction; no claim of current-model accuracy'})
    snapshot=output/'source_code';snapshot.mkdir()
    paths=[Path(__file__),Path(__file__).with_name('context_budget.py'),Path(__file__).with_name('snapshot_benchmark.py'),
        ROOT/'src/retrieval/hybrid_retrieval.py',ROOT/'src/normalization/normalize_entities.py']
    for p in paths:(snapshot/p.name).write_bytes(p.read_bytes())
    atomic_json(output/'summary.json',{'n_questions':45,'kg_records':len(rows),'all_methods_records':len(rows)+len(base),
        'max_context_tokens':max(r['context_tokens'] for r in rows),'empty_kg_contexts':sum(not r['context'] for r in rows),
        'oversized_first_record':sum(r['prefix_exceeds_budget'] for r in rows),'graph_setup_seconds':setup,
        'normalized_nodes':len(graph.nodes),'raw_nodes':len(raw.nodes),'ambiguous_relations_skipped':graph.invalid_relations,
        'kg_verified_retrieval_identical_to_kg':True,'claim_verification_executed':False,'actual_api_calls':0,
        'quality_scores_computed':False,'ready_for_confirmatory_reporting':False,
        'limits':'Snapshot graph diagnostics, not Neo4j latency, independent QA scores, repeated-run study or released SOTA comparison.'})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('dataset','vector','baseline-contexts','cache','output'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args();run(**vars(args))
