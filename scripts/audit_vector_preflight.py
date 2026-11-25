"""Check complete matched retrieval artifacts; compute no relevance/QA metric."""
import argparse
import collections
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from workflow_io import read_json,file_hash,canonical_hash,atomic_json


def audit(root):
    manifest=read_json(root/'manifest.json');summary=read_json(root/'summary.json')
    chunks=[json.loads(s) for s in (root/'chunks.jsonl').read_text(encoding='utf-8').split('\n') if s]
    rows=[json.loads(s) for s in (root/'retrieval_records.jsonl').read_text(encoding='utf-8').split('\n') if s]
    if len(chunks)!=manifest['n_chunks'] or canonical_hash([c['shared_retrieval_text'] for c in chunks])!=manifest['shared_texts_sha256']:
        raise ValueError('Shared retrieval texts changed')
    vectors=np.load(root/'embeddings.npy',allow_pickle=False)
    if list(vectors.shape)!=manifest['embedding_shape'] or file_hash(root/'embeddings.npy')!=summary['embedding_file_sha256']:
        raise ValueError('Dense vectors changed')
    if not np.isfinite(vectors).all() or not np.allclose(np.linalg.norm(vectors,axis=1),1,atol=1e-4):raise ValueError('Invalid vectors')
    grid={};top1={}
    for row in rows:
        key=(row['question_id'],row['method'])
        if key in grid:raise ValueError('Duplicate result')
        grid[key]=row
        if any(k in row for k in ('ground_truth','reference_answer','chatbot_answer')):raise ValueError('Answer leakage into retrieval artifact')
        if row['generation_executed'] or row['quality_score'] is not None:raise ValueError('Unexpected generation or quality scoring')
        hits=row['ranked_hits'];ids=[i for i,score in hits]
        if len(ids)>manifest['top_k'] or len(ids)!=len(set(ids)) or any(type(i) is not int or not 0<=i<len(chunks) for i in ids):raise ValueError('Invalid hits')
        context=row['retrieved_context']
        if len(context)>len(ids) or [c['chunk_id'] for c in context]!=ids[:len(context)]:raise ValueError('Context/ranking mismatch')
        for c in context:
            if c!={**chunks[c['chunk_id']]['source'],'chunk_id':c['chunk_id']}:raise ValueError('Original source context changed')
        size=sum(len(json.dumps(c,ensure_ascii=False)) for c in context)
        if size!=row['context_chars'] or size>manifest['context_char_budget']:raise ValueError('Context budget mismatch')
        top1[key]=ids[0] if ids else None
    expected={(q,m) for q in range(1,manifest['n_questions']+1) for m in ('bm25','vector')}
    if set(grid)!=expected:raise ValueError('Incomplete question/method grid')
    for q in range(1,manifest['n_questions']+1):
        if grid[q,'bm25']['shared_query']!=grid[q,'vector']['shared_query']:raise ValueError('Methods received different queries')
    return {'status':'passed','n_questions':manifest['n_questions'],'n_records':len(rows),'embedding_shape':list(vectors.shape),
        'top1_different_between_methods':sum(top1[q,'bm25']!=top1[q,'vector'] for q in range(1,manifest['n_questions']+1)),
        'actual_api_calls':0,'quality_scores_computed':False,
        'interpretation':'Artifact integrity and execution diagnostics only; ranking differences do not prove relevance or superiority.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Fresh audit report required')
    atomic_json(args.output,audit(args.run))
