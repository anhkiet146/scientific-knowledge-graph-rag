"""Offline matched BM25/Vector retrieval on the repaired source corpus."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/evaluation')]
from workflow_io import read_json,atomic_json,file_hash,canonical_hash
from snapshot_benchmark import load_chunks,BM25Index
from context_budget import pack_v2
from vector_preflight import dense_topk
from fair_runtime import clip_embedding_inputs


def verify_source(dataset):
    manifest=read_json(dataset/'manifest.json');root=dataset.resolve()
    if manifest.get('status') not in {'source_only_extraction_and_indices_pending','source_snapshot_existing_extractions'}:
        raise ValueError('Expected a hash-bound source snapshot')
    expected={r['path'] for r in manifest['files']}
    actual={p.relative_to(root).as_posix() for p in (root/'corpus').glob('*.json')}
    if len(expected)!=manifest['documents'] or expected!=actual:
        raise ValueError('Source file inventory mismatch')
    for row in manifest['files']:
        path=(root/row['path']).resolve()
        if not path.is_relative_to(root/'corpus') or file_hash(path)!=row['sha256']:
            raise ValueError('Source file changed or unsafe path')
    if file_hash(root/'questions.py')!=manifest['questions_sha256']:raise ValueError('Questions changed')
    return manifest


def lines(path):return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def run(dataset,prior_vector,queries,tokenizer_cache,output):
    print('Verifying source and model snapshots',flush=True)
    import numpy as np
    if output.exists():raise ValueError('Fresh output required')
    source_manifest=verify_source(dataset)
    prior=read_json(prior_vector/'manifest.json');prior_summary=read_json(prior_vector/'summary.json')
    if file_hash(prior_vector/'embeddings.npy')!=prior_summary['embedding_file_sha256']:
        raise ValueError('Prior vector cache changed')
    model_path=Path(prior['model_path'])
    for name,digest in prior['model_files_sha256'].items():
        if file_hash(model_path/name)!=digest:raise ValueError('Pinned model changed')
    cases={}
    for row in lines(queries):
        value=(row['question'],row['shared_query'])
        if row['question_id'] in cases and cases[row['question_id']]!=value:raise ValueError('Queries differ across methods')
        cases[row['question_id']]=value
    if set(cases)!=set(range(1,46)):raise ValueError('45 unique shared queries required')
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',TIKTOKEN_CACHE_DIR=str(tokenizer_cache.resolve()))
    print('Loading offline embedding runtime',flush=True)
    import torch
    from sentence_transformers import SentenceTransformer
    import tiktoken,tiktoken.load
    def offline(url):raise RuntimeError('Tokenizer download disabled')
    tiktoken.load.read_file=offline
    encoder=tiktoken.get_encoding('o200k_base')
    torch.set_num_threads(4)
    print('Loading pinned local model',flush=True)
    model=SentenceTransformer(str(model_path),device='cpu',local_files_only=True,trust_remote_code=False)
    limit=model.max_seq_length-model.tokenizer.num_special_tokens_to_add(pair=False)
    def clipped(text):
        return clip_embedding_inputs(model.tokenizer,[text],model.max_seq_length)[0][0]
    old=lines(prior_vector/'chunks.jsonl');old_matrix=np.load(prior_vector/'embeddings.npy',allow_pickle=False)
    if len(old)!=len(old_matrix):raise ValueError('Prior cache dimensions differ')
    if canonical_hash([r['shared_retrieval_text'] for r in old])!=prior['shared_texts_sha256']:
        raise ValueError('Prior shared texts changed')
    old_lookup={canonical_hash([row['source'],row['shared_retrieval_text']]):i for i,row in enumerate(old)}
    chunks=load_chunks(dataset/'corpus')
    print('Preparing shared texts:',len(chunks),flush=True)
    texts=[clipped(c['title']+' '+c['text']) for c in chunks]
    matrix=np.zeros((len(chunks),old_matrix.shape[1]),dtype=old_matrix.dtype);missing=[];reused=0
    for i,(chunk,text) in enumerate(zip(chunks,texts)):
        key=canonical_hash([chunk,text])
        if key in old_lookup:matrix[i]=old_matrix[old_lookup[key]];reused+=1
        else:missing.append(i)
    print('Chunks:',len(chunks),'cached:',reused,'new embeddings:',len(missing),flush=True)
    start=time.perf_counter()
    if missing:matrix[missing]=model.encode([texts[i] for i in missing],batch_size=32,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)
    embedding_seconds=time.perf_counter()-start
    dense_topk(matrix,matrix[0],1)
    bm=BM25Index(texts);records=[]
    output.mkdir(parents=True)
    np.save(output/'embeddings.npy',matrix,allow_pickle=False)
    with (output/'chunks.jsonl').open('w',encoding='utf-8') as stream:
        for i,(source,text) in enumerate(zip(chunks,texts)):stream.write(json.dumps({'chunk_id':i,'source':source,'shared_retrieval_text':text},ensure_ascii=False)+'\n')
    for qid,(question,query) in sorted(cases.items()):
        if len(model.tokenizer(query,add_special_tokens=True)['input_ids'])>model.max_seq_length:raise ValueError('Frozen query exceeds encoder')
        q=model.encode([query],normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)[0]
        for method,hits in [('bm25',bm.search(query,8)),('vector',dense_topk(matrix,q,8))]:
            context,text,count,audit=pack_v2([{**chunks[i],'chunk_id':i} for i,_ in hits],lambda t:encoder.encode(t,disallowed_special=()),2000)
            records.append({'question_id':qid,'question':question,'shared_query':query,'method':method,
                'ranked_hits':hits,'context':context,'context_json':text,'context_sha256':canonical_hash(text),
                'context_tokens':count,'packing_audit':audit,'quality_score':None})
    path=output/'contexts.jsonl';path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    verify_source(dataset)
    atomic_json(output/'manifest.json',{'status':'retrieval_diagnostic_only','documents':source_manifest['documents'],
        'dataset_manifest_sha256':file_hash(dataset/'manifest.json'),'prior_vector_manifest_sha256':file_hash(prior_vector/'manifest.json'),
        'queries_sha256':file_hash(queries),'contexts_sha256':file_hash(path),'model_path':str(model_path),
        'model_files_sha256':prior['model_files_sha256'],'code_sha256':file_hash(Path(__file__)),
        'embedding_sha256':file_hash(output/'embeddings.npy'),'chunks_sha256':file_hash(output/'chunks.jsonl'),
        'methods':['bm25','vector'],'questions':45,'records':len(records),'chunks':len(chunks),'reused_embeddings':reused,
        'new_embeddings':len(missing),'new_embedding_seconds':embedding_seconds,'context_limit_tokens':2000,'tokenizer':'o200k_base',
        'scope_policy':'whole repaired corpus, no title scope for either method',
        'input_policy':'same clipped title+passage index text; same frozen query; original whole source chunks packed identically',
        'api_calls':0,'quality_scores_computed':False,
        'limits':'New488source corpus, not live489 or frozen482. Mixed historical parser and PDF-page text. No KG/SOTA full comparison, independent scoring, repeated runs or end-to-end latency claim.'})
    print('Saved',len(records),'retrieval contexts; API calls:0',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('dataset','prior-vector','queries','tokenizer-cache','output'):parser.add_argument('--'+name,type=Path,required=True)
    run(**vars(parser.parse_args()))
