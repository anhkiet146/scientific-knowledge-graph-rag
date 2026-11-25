"""Repack all methods with identical v2 policy and audit a lossless ledger. Zero API."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src/extraction'),str(ROOT/'src/evaluation'),str(ROOT/'src/retrieval'),str(ROOT/'src/normalization')]
from workflow_io import atomic_json,canonical_hash,file_hash
from prepare_review_dataset import verify
from evidence_ledger import build_ledger
from snapshot_benchmark import SnapshotGraph
from hybrid_retrieval import build_query_plan,rerank_candidates
from kg_ablation_preflight import VARIANTS
from context_budget import pack_v2,evidence_units


def lines(path):return [json.loads(s) for s in path.read_text(encoding='utf-8').split('\n') if s]


def write_lines(path,rows):
    with path.open('w',encoding='utf-8') as stream:
        for row in rows:stream.write(json.dumps(row,ensure_ascii=False)+'\n')


def run(dataset,vector,cache,output):
    if output.exists():raise ValueError('Fresh output required')
    verify(dataset)
    manifest=json.loads((vector/'manifest.json').read_text(encoding='utf-8'))
    if manifest['dataset_manifest_sha256']!=file_hash(dataset/'manifest.json'):raise ValueError('Dataset mismatch')
    # Fail closed instead of downloading tokenizer assets.
    import tiktoken.load
    def no_network(*args,**kwargs):raise RuntimeError('Tokenizer cache missing: no network allowed in offline stage')
    tiktoken.load.read_file=no_network
    os.environ['TIKTOKEN_CACHE_DIR']=str(cache.resolve())
    import tiktoken
    enc=tiktoken.get_encoding('o200k_base')
    encode=lambda text:enc.encode(text,disallowed_special=())
    output.mkdir(parents=True)
    chunks={r['chunk_id']:r['source'] for r in lines(vector/'chunks.jsonl')}
    base=lines(vector/'retrieval_records.jsonl');queries={};rows=[]
    def add(qid,question,query,method,candidates):
        context,text,count,audit=pack_v2(candidates,encode)
        rows.append({'question_id':qid,'question':question,'shared_query':query,'method':method,
                     'context':context,'context_json':text,'context_tokens':count,'context_sha256':canonical_hash(text),
                     'packing_audit':audit,'generation_status':'not_executed','quality_score':None})
    for row in base:
        qid=row['question_id'];value=(row['question'],row['shared_query'])
        if qid in queries and queries[qid]!=value:raise ValueError('Query mismatch')
        queries[qid]=value
        candidates=[dict(chunks[index],chunk_id=index) for index,_ in row['ranked_hits']]
        add(qid,*value,row['method'],candidates)
    graph=SnapshotGraph(dataset/'extracted',preserve_evidence=True);raw=SnapshotGraph(dataset/'extracted',normalize=False,preserve_evidence=True)
    for qid,(question,query) in sorted(queries.items()):
        for method,options in VARIANTS.items():
            g=raw if options.get('raw') else graph
            candidates=g.retrieve(query,hops=options.get('hops',2))
            ranked=rerank_candidates(query,build_query_plan(query,{'keywords':[query]}),candidates,max_context=8,signal_multipliers=options.get('multipliers'))
            add(qid,question,query,method,evidence_units(ranked))
    expected={(q,m) for q in range(1,46) for m in ('bm25','vector',*VARIANTS)}
    if len(rows)!=360 or {(r['question_id'],r['method']) for r in rows}!=expected:raise ValueError('Invalid grid')
    for qid in queries:
        subset={r['method']:r for r in rows if r['question_id']==qid}
        if subset['kg']['context_json']!=subset['kg_verified']['context_json']:raise ValueError('Paired context changed')
    write_lines(output/'all_eight_methods.jsonl',rows)
    nodes,relations,audit=build_ledger(dataset/'extracted')
    write_lines(output/'normalized_evidence_nodes.jsonl',nodes);write_lines(output/'normalized_evidence_relations.jsonl',relations)
    atomic_json(output/'normalization_audit.json',audit)
    verify(dataset)
    source_paths=[Path(__file__),ROOT/'src/evaluation/context_budget.py',ROOT/'src/evaluation/snapshot_benchmark.py',ROOT/'src/normalization/evidence_ledger.py',ROOT/'src/normalization/normalize_entities.py',ROOT/'src/retrieval/hybrid_retrieval.py']
    snapshot=output/'source_code';snapshot.mkdir()
    for path in source_paths:(snapshot/path.name).write_bytes(path.read_bytes())
    atomic_json(output/'manifest.json',{'protocol_id':'offline-repacking-v2','dataset_sha256':file_hash(dataset/'manifest.json'),
        'vector_manifest_sha256':file_hash(vector/'manifest.json'),'vector_records_sha256':file_hash(vector/'retrieval_records.jsonl'),
        'chunks_sha256':file_hash(vector/'chunks.jsonl'),'code_sha256':{str(p.relative_to(ROOT)):file_hash(p) for p in source_paths},
        'policy':'Stable skip-nonfitting whole-record packing v2 for ALL eight methods, same 2000 proxy-token budget. KG uses round-robin source-scoped entity occurrences then relation occurrences; index retains all descriptions. New representation, not historical replay.',
        'corpus':'frozen historical extraction; evidence ledger preserves occurrences but is not newly approved gold',
        'contexts_sha256':file_hash(output/'all_eight_methods.jsonl'),'actual_api_calls':0})
    summary={'records':len(rows),'empty_contexts':{m:sum(not r['context'] for r in rows if r['method']==m) for m in ('bm25','vector',*VARIANTS)},
             'max_tokens':max(r['context_tokens'] for r in rows),'actual_api_calls':0,'quality_scores_computed':False,
             'limits':'Selection diagnostics only. Same token budget does not imply identical evidence formats. Ledger is an audit layer, not a replacement graph index.'}
    atomic_json(output/'summary.json',summary);print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('dataset','vector','cache','output'):p.add_argument('--'+flag,type=Path,required=True)
    run(**vars(p.parse_args()))
