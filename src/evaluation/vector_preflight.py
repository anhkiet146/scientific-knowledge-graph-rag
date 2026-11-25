"""Matched local BM25/dense retrieval diagnostics; no generation or quality scores."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src/extraction')]
from prepare_review_dataset import verify,read_questions
from snapshot_benchmark import load_chunks,BM25Index
from workflow_io import canonical_hash,file_hash,atomic_json


def dense_topk(embeddings,query,k):
    matrix=np.asarray(embeddings);q=np.asarray(query)
    if matrix.ndim!=2 or q.shape!=(matrix.shape[1],) or not len(matrix) or k<1:
        raise ValueError('Invalid dense index dimensions or k')
    if not np.isfinite(matrix).all() or not np.isfinite(q).all():raise ValueError('Nonfinite embedding')
    if not np.allclose(np.linalg.norm(matrix,axis=1),1,atol=1e-4) or not np.isclose(np.linalg.norm(q),1,atol=1e-4):
        raise ValueError('Unit-normalized vectors required')
    scores=matrix@q;ids=np.lexsort((np.arange(len(scores)),-scores))[:k]
    return [(int(i),float(scores[i])) for i in ids]


def bound_context(chunks,hits,budget=12000):
    if budget<1:raise ValueError('Positive context budget required')
    selected=[];size=0
    for index,score in hits:
        row={**chunks[index],'chunk_id':index}
        length=len(json.dumps(row,ensure_ascii=False))
        if size+length>budget:break
        selected.append(row);size+=length
    return selected,size


def run(args):
    dataset=args.dataset.resolve();model_dir=args.model.resolve();output=args.output.resolve()
    if output.exists():raise ValueError('Fresh output directory required')
    if not model_dir.is_dir() or not (model_dir/'model.safetensors').is_file():raise ValueError('Complete local model required')
    if args.top_k<1 or args.batch_size<1 or args.threads<1:raise ValueError('Positive execution settings required')
    for source in (dataset,model_dir):
        if source.is_relative_to(output) or output.is_relative_to(source):raise ValueError('Separate output required')
    print('Verifying frozen dataset',flush=True);verify(dataset)
    questions=[{'question_id':i,'question':q['question']} for i,q in enumerate(read_questions(dataset/'questions.py'),1)]
    translations=None
    if args.translations:translations=json.loads(args.translations.read_text(encoding='utf-8'))
    for row in questions:
        text=row['question']
        if translations is not None:
            translated=translations.get(hashlib.sha1(text.encode()).hexdigest())
            if not isinstance(translated,str) or not translated.strip():raise ValueError('Missing cached translation')
            text+=' '+translated
        row['retrieval_query']=text
    # No hub download, remote code, API or fallback model is allowed.
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1';os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    print('Loading local embedding libraries',flush=True)
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(args.threads)
    start=time.perf_counter()
    print('Loading cached model, CPU only',flush=True)
    model=SentenceTransformer(str(model_dir),device='cpu',local_files_only=True,trust_remote_code=False)
    model_seconds=time.perf_counter()-start
    model_files={p.relative_to(model_dir).as_posix():file_hash(p) for p in sorted(model_dir.rglob('*')) if p.is_file()}
    chunks=load_chunks(dataset/'corpus');raw_texts=[c['title']+' '+c['text'] for c in chunks]
    limit=int(model.max_seq_length)-model.tokenizer.num_special_tokens_to_add(pair=False)
    def shared_text(text):
        ids=model.tokenizer(text,add_special_tokens=False,truncation=True,max_length=limit)['input_ids']
        result=model.tokenizer.decode(ids,skip_special_tokens=False,clean_up_tokenization_spaces=False)
        if len(model.tokenizer(result,add_special_tokens=True)['input_ids'])>model.max_seq_length:
            raise ValueError('Shared tokenizer roundtrip exceeds encoder limit')
        return result
    print('Preparing matched texts:',len(chunks),'chunks',flush=True)
    common=[shared_text(t) for t in raw_texts]
    bm_start=time.perf_counter();bm25=BM25Index(common);bm_seconds=time.perf_counter()-bm_start
    print('Encoding corpus vectors',flush=True)
    start=time.perf_counter();embeddings=model.encode(common,batch_size=args.batch_size,normalize_embeddings=True,
        convert_to_numpy=True,show_progress_bar=True)
    encode_seconds=time.perf_counter()-start
    dense_topk(embeddings,embeddings[0],1)  # Validate all corpus vectors before producing records.
    output.mkdir(parents=True)
    manifest={'protocol_id':'matched-dense-retrieval-preflight-v1','dataset_manifest_sha256':file_hash(dataset/'manifest.json'),
        'model_path':str(model_dir),'model_files_sha256':model_files,'device':'cpu','torch_threads':args.threads,
        'packages':{name:importlib.metadata.version(name) for name in ('numpy','torch','sentence-transformers','transformers')},
        'platform':platform.platform(),'python':sys.version,'n_chunks':len(chunks),'n_questions':len(questions),
        'top_k':args.top_k,'context_char_budget':12000,'model_max_seq_length':model.max_seq_length,
        'shared_index_input':'Same title+passage, tokenized/truncated/decoded once for BOTH methods; original source chunk returned as context.',
        'query_input':'Same clipped query for both; original question plus cached English translation' if translations else 'Same clipped original question for both',
        'translation_sha256':file_hash(args.translations) if args.translations else None,
        'shared_texts_sha256':canonical_hash(common),'embedding_shape':list(embeddings.shape),
        'code_sha256':{p.name:file_hash(p) for p in [Path(__file__),ROOT/'src/evaluation/snapshot_benchmark.py',ROOT/'scripts/prepare_review_dataset.py']},
        'reference_status':'No reference answers used for retrieval; independent labels not completed'}
    atomic_json(output/'manifest.json',manifest);np.save(output/'embeddings.npy',embeddings,allow_pickle=False)
    with (output/'chunks.jsonl').open('w',encoding='utf-8') as stream:
        for index,(chunk,text) in enumerate(zip(chunks,common)):
            stream.write(json.dumps({'chunk_id':index,'source':chunk,'shared_retrieval_text':text},ensure_ascii=False)+'\n')
    records=[]
    for row in questions:
        start=time.perf_counter();query=shared_text(row['retrieval_query']);prepare_seconds=time.perf_counter()-start
        start=time.perf_counter();bm_hits=bm25.search(query,args.top_k);bm_online=time.perf_counter()-start
        start=time.perf_counter();q=model.encode([query],normalize_embeddings=True,convert_to_numpy=True)[0];q_seconds=time.perf_counter()-start
        start=time.perf_counter();vector_hits=dense_topk(embeddings,q,args.top_k);vector_online=time.perf_counter()-start
        for method,hits,seconds in [('bm25',bm_hits,bm_online),('vector',vector_hits,vector_online)]:
            context,size=bound_context(chunks,hits)
            records.append({**row,'shared_query':query,'method':method,'ranked_hits':hits,'retrieved_context':context,
                'context_chars':size,'query_prepare_seconds':prepare_seconds,'search_seconds':seconds,
                'query_embedding_seconds':q_seconds if method=='vector' else 0,'generation_executed':False,'quality_score':None})
        print('retrieval',row['question_id'],'/',len(questions),flush=True)
    with (output/'retrieval_records.jsonl').open('w',encoding='utf-8') as stream:
        for row in records:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    verify(dataset)
    if any(file_hash(model_dir/name)!=digest for name,digest in model_files.items()):raise ValueError('Model changed during run')
    atomic_json(output/'summary.json',{'stage':'retrieval_only','methods':['bm25','vector'],'n_questions':len(questions),
        'n_records':len(records),'n_chunks':len(chunks),'empty_contexts':sum(not r['retrieved_context'] for r in records),
        'model_load_seconds':model_seconds,'bm25_index_seconds':bm_seconds,'corpus_embedding_seconds':encode_seconds,
        'embedding_file_sha256':file_hash(output/'embeddings.npy'),'actual_api_calls':0,'generation_calls':0,'quality_scores_computed':False,
        'limitations':'Single-run local retrieval diagnostics, not QA quality or end-to-end latency. English cached model; no tuning, independent labels or released GraphRAG baseline. Local frozen corpus uses historical extraction, not newly approved coordinate candidates.'})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True);parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--translations',type=Path)
    parser.add_argument('--top-k',type=int,default=8);parser.add_argument('--batch-size',type=int,default=32)
    parser.add_argument('--threads',type=int,default=4);run(parser.parse_args())
