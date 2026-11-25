import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/evaluation'),str(ROOT/'src/retrieval'),str(ROOT/'scripts')]
from workflow_io import read_json,atomic_json,file_hash,canonical_hash
from prepare_review_dataset import verify
from snapshot_benchmark import BM25Index
from paper_scope import PaperScope
from context_budget import pack_v2
from vector_preflight import dense_topk


def lines(path):return [json.loads(s) for s in path.read_text(encoding='utf-8').split('\n') if s]


def run(dataset,vector,queries,cache,output):
    if output.exists():raise ValueError('Fresh output required')
    verify(dataset);manifest=read_json(vector/'manifest.json');prior=read_json(vector/'summary.json')
    if manifest['dataset_manifest_sha256']!=file_hash(dataset/'manifest.json'):raise ValueError('Corpus mismatch')
    if prior['embedding_file_sha256']!=file_hash(vector/'embeddings.npy'):raise ValueError('Cached embeddings changed')
    model_path=Path(manifest['model_path'])
    if any(file_hash(model_path/name)!=digest for name,digest in manifest['model_files_sha256'].items()):raise ValueError('Embedding weights changed')
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',TIKTOKEN_CACHE_DIR=str(cache.resolve()))
    import tiktoken.load
    def offline(*args,**kwargs):raise RuntimeError('Tokenizer cache required')
    tiktoken.load.read_file=offline
    import tiktoken
    enc=tiktoken.get_encoding('o200k_base');encode=lambda text:enc.encode(text,disallowed_special=())
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(4);torch.manual_seed(20261116)
    start=time.perf_counter();model=SentenceTransformer(str(model_path),device='cpu',local_files_only=True,trust_remote_code=False);model_load=time.perf_counter()-start
    records=lines(vector/'chunks.jsonl');embeddings=np.load(vector/'embeddings.npy',allow_pickle=False)
    if [r['chunk_id'] for r in records]!=list(range(len(records))) or len(records)!=len(embeddings):raise ValueError('Chunk index mismatch')
    dense_topk(embeddings,embeddings[0],1)
    shared_texts=[r['shared_retrieval_text'] for r in records]
    if canonical_hash(shared_texts)!=manifest['shared_texts_sha256']:raise ValueError('Shared index texts changed')
    start=time.perf_counter();index=BM25Index(shared_texts);bm_build=time.perf_counter()-start
    title_files=sorted((dataset/'corpus').glob('*.json'));titles={p.name:read_json(p).get('title','') for p in title_files};scoper=PaperScope(titles)
    papers=[Path(r['source']['paper_id']).with_suffix('.json').name for r in records]
    cases={}
    for r in lines(queries):
        value=(r['question'],r['shared_query'])
        if r['question_id'] in cases and cases[r['question_id']]!=value:raise ValueError('Query changed across methods')
        cases[r['question_id']]=value
    if set(cases)!=set(range(1,46)):raise ValueError('45 queries required')
    output.mkdir(parents=True);rows=[];query_vectors=[]
    for qid,(question,query) in sorted(cases.items()):
        if len(model.tokenizer(query,add_special_tokens=True)['input_ids'])>model.max_seq_length:raise ValueError('Frozen query would be truncated')
        start=time.perf_counter()
        scope=scoper.select(query);allowed=scope['allowed_papers'];ids=np.array([i for i,p in enumerate(papers) if allowed is None or p in allowed],dtype=int)
        scope_seconds=time.perf_counter()-start
        start=time.perf_counter();hits=[(i,s) for i,s in index.search(query,len(records)) if allowed is None or papers[i] in allowed][:8];bm_search=time.perf_counter()-start
        start=time.perf_counter();q=model.encode([query],normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)[0];query_seconds=time.perf_counter()-start;query_vectors.append(q)
        start=time.perf_counter();scores=embeddings[ids]@q if len(ids) else np.array([]);order=np.lexsort((ids,-scores))[:8]
        vector_hits=[(int(ids[i]),float(scores[i])) for i in order];vector_search=time.perf_counter()-start
        for method,ranked,seconds in [('bm25',hits,bm_search),('vector',vector_hits,vector_search)]:
            start=time.perf_counter()
            context,text,count,audit=pack_v2([{**records[i]['source'],'chunk_id':i} for i,_ in ranked],encode)
            packing_seconds=time.perf_counter()-start
            rows.append({'question_id':qid,'question':question,'shared_query':query,'method':method,'context':context,'context_json':text,
                'context_tokens':count,'context_sha256':canonical_hash(text),'paper_scope':scope,'ranked_hits':ranked,'packing_audit':audit,
                'search_seconds':seconds,'query_embedding_seconds':query_seconds if method=='vector' else 0,
                'timing':{'source_selection_seconds':scope_seconds,'search_seconds':seconds,
                    'query_embedding_seconds':query_seconds if method=='vector' else 0,'packing_seconds':packing_seconds,
                    'retrieval_stage_sum_seconds':scope_seconds+seconds+packing_seconds+(query_seconds if method=='vector' else 0),
                    'scope':'Sum of measured retrieval stages; shared source-selection cost attributed to each method; excludes setup, generation and verifier. Not request wall time.'},
                'generation_status':'not_executed','quality_score':None})
        print('baselines',qid,'complete',flush=True)
    with (output/'contexts.jsonl').open('w',encoding='utf-8') as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    np.save(output/'query_embeddings.npy',np.array(query_vectors),allow_pickle=False)
    atomic_json(output/'manifest.json',{'code_sha256':file_hash(Path(__file__)),'dataset_manifest_sha256':file_hash(dataset/'manifest.json'),
        'vector_manifest_sha256':file_hash(vector/'manifest.json'),'chunks_sha256':file_hash(vector/'chunks.jsonl'),'embedding_sha256':file_hash(vector/'embeddings.npy'),
        'queries_sha256':file_hash(queries),'model_files_sha256':manifest['model_files_sha256'],'device':'cpu','threads':4,
        'packages':{p:importlib.metadata.version(p) for p in ['numpy','torch','sentence-transformers','transformers','tiktoken']},
        'paper_scope_sha256':file_hash(ROOT/'src/retrieval/paper_scope.py'),'packing_sha256':file_hash(ROOT/'src/evaluation/context_budget.py'),
        'policy':'Same frozen shared query and title-derived paper scope as KG; same cached MiniLM corpus vectors, shared clipped title+passage index inputs for BM25/Vector; top8 whole source chunks, pack_v2 2000 tokens. No labels or generator calls.',
        'timing':'Warm cached corpus embeddings; record historical indexing separately. Current model load/BM25 build, query encoding and search not end-to-end generation.'})
    summary={'questions':45,'records':len(rows),'empty_contexts':{m:sum(not r['context'] for r in rows if r['method']==m) for m in ['bm25','vector']},
        'max_tokens':max(r['context_tokens'] for r in rows),'model_load_seconds':model_load,'bm25_build_seconds':bm_build,
        'actual_api_calls':0,'quality_scores_computed':False}
    atomic_json(output/'summary.json',summary);verify(dataset)
    if file_hash(vector/'embeddings.npy')!=prior['embedding_file_sha256']:raise ValueError('Embedding file changed during run')
    print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for flag in ('dataset','vector','queries','cache','output'):p.add_argument('--'+flag,type=Path,required=True)
    run(**vars(p.parse_args()))
