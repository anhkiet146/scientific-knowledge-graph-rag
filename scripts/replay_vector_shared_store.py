"""Replay Vector retrieval on the pinned store selected for the LightRAG track."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/evaluation')]
from workflow_io import read_json,file_hash,atomic_json,canonical_hash
from context_budget import pack_v2


def run(prior,cache,output):
    import numpy as np
    from nano_vectordb import NanoVectorDB
    if output.exists():raise ValueError('Fresh output required')
    manifest=read_json(prior/'manifest.json')
    for name,field in [('contexts.jsonl','contexts_sha256'),('chunks.jsonl','chunks_sha256'),('embeddings.npy','embedding_sha256')]:
        if file_hash(prior/name)!=manifest[field]:raise ValueError('Prior artifact changed')
    if importlib.metadata.version('nano-vectordb')!='0.0.4.3':raise ValueError('Pinned vector store required')
    model_path=Path(manifest['model_path'])
    for name,digest in manifest['model_files_sha256'].items():
        if file_hash(model_path/name)!=digest:raise ValueError('Pinned model changed')
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',TIKTOKEN_CACHE_DIR=str(cache.resolve()))
    import torch
    from sentence_transformers import SentenceTransformer
    import tiktoken,tiktoken.load
    def offline(url):raise RuntimeError('Tokenizer download disabled')
    tiktoken.load.read_file=offline
    enc=tiktoken.get_encoding('o200k_base');torch.set_num_threads(4)
    model=SentenceTransformer(str(model_path),device='cpu',local_files_only=True,trust_remote_code=False)
    chunks=[json.loads(s) for s in (prior/'chunks.jsonl').read_text(encoding='utf-8').splitlines()]
    rows=[json.loads(s) for s in (prior/'contexts.jsonl').read_text(encoding='utf-8').splitlines()]
    matrix=np.load(prior/'embeddings.npy',allow_pickle=False)
    if len(chunks)!=len(matrix):raise ValueError('Index dimensions differ')
    output.mkdir(parents=True)
    store=NanoVectorDB(matrix.shape[1],metric='cosine',storage_file=str(output/'vectors.json'))
    store.upsert([{'__id__':str(i),'__vector__':v.copy()} for i,v in enumerate(matrix)])
    store.save();result=[];changed=[]
    for row in rows:
        if row['method']=='bm25':result.append(row);continue
        q=model.encode([row['shared_query']],normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)[0]
        hits=store.query(q,top_k=8,better_than_threshold=-1.0)
        context,text,count,audit=pack_v2([{**chunks[int(h['__id__'])]['source'],'chunk_id':int(h['__id__'])} for h in hits],lambda t:enc.encode(t,disallowed_special=()),2000)
        if text!=row['context_json']:changed.append(row['question_id'])
        result.append({**row,'context':context,'context_json':text,'context_sha256':canonical_hash(text),'context_tokens':count,
                       'packing_audit':audit,'ranked_hits':[(int(h['__id__']),float(h['__metrics__'])) for h in hits]})
    path=output/'contexts.jsonl';path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in result),encoding='utf-8')
    atomic_json(output/'manifest.json',{'dataset_manifest_sha256':manifest['dataset_manifest_sha256'],
        'contexts_sha256':file_hash(path),'source_manifest_sha256':file_hash(prior/'manifest.json'),
        'store_sha256':file_hash(output/'vectors.json'),'backend':'nano-vectordb==0.0.4.3','metric':'cosine',
        'threshold':-1.0,'dimension':matrix.shape[1],'normalize':True,'device':'cpu','threads':4,
        'model_files_sha256':manifest['model_files_sha256'],'queries_sha256':manifest['queries_sha256'],
        'records':len(result),'changed_vector_context_questions':changed,'api_calls':0,'quality_scores_computed':False,
        'code_sha256':file_hash(Path(__file__)),'limits':'Store alignment with the planned LightRAG configuration only; full LightRAG indexing and KG488 retrieval remain incomplete. Not a completed four-method comparison.'})
    print('Saved',len(result),'contexts; changed Vector contexts:',changed,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('prior','cache','output'):p.add_argument('--'+name,type=Path,required=True)
    run(**vars(p.parse_args()))
