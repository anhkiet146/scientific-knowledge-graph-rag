"""Token-bound contexts from existing retrieval; never generates answers."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'scripts')]
from workflow_io import read_json,canonical_hash,file_hash,atomic_json
from audit_vector_preflight import audit


def bounded(chunks,hits,encode,limit=2000):
    if type(limit) is not int or limit<1:raise ValueError('Positive token limit required')
    chosen=[];seen=set()
    for index,_ in hits:
        if type(index) is not int or not 0<=index<len(chunks) or index in seen:raise ValueError('Invalid or duplicate source chunk ID')
        seen.add(index)
        row={'chunk_id':index,**chunks[index]['source']}
        candidate=chosen+[row]
        if len(encode(json.dumps(candidate,ensure_ascii=False,sort_keys=True,separators=(',',':'))))>limit:break
        chosen=candidate
    text=json.dumps(chosen,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    if len(encode(text))>limit:raise ValueError('Even the empty context exceeds token limit')
    return chosen,text,len(encode(text))


def run(retrieval,design,cache,output):
    if output.exists():raise ValueError('Fresh context output required')
    audit(retrieval)
    os.environ['TIKTOKEN_CACHE_DIR']=str(cache.resolve())
    import tiktoken
    if importlib.metadata.version('tiktoken')!='0.14.0':raise ValueError('Pinned tokenizer tiktoken 0.14.0 required')
    encoding=tiktoken.get_encoding('o200k_base')
    digest=hashlib.sha256()
    for token,rank in sorted(encoding._mergeable_ranks.items(),key=lambda item:item[1]):
        digest.update(len(token).to_bytes(4,'big'));digest.update(token);digest.update(rank.to_bytes(4,'big'))
    digest.update(json.dumps(encoding._special_tokens,sort_keys=True).encode())
    tokenizer={'package':'tiktoken','version':'0.14.0','encoding':'o200k_base','vocabulary_sha256':digest.hexdigest(),
        'interpretation':'Common proxy tokenizer for context budgeting; not Gemini provider token accounting'}
    def encode(text):return encoding.encode(text,disallowed_special=())
    chunks=[json.loads(s) for s in (retrieval/'chunks.jsonl').read_text(encoding='utf-8').split('\n') if s]
    records=[json.loads(s) for s in (retrieval/'retrieval_records.jsonl').read_text(encoding='utf-8').split('\n') if s]
    expected={(q,m) for q in range(1,46) for m in ('bm25','vector')};seen=set();result=[]
    for row in records:
        key=(row['question_id'],row['method'])
        if key not in expected or key in seen:raise ValueError('Unexpected/duplicate retrieval row')
        seen.add(key)
        context,text,count=bounded(chunks,row['ranked_hits'],encode)
        result.append({'question_id':key[0],'method':key[1],'question':row['question'],'context':context,
            'context_json':text,'context_sha256':canonical_hash(text),'context_tokens':count,
            'generation_status':'not_executed','quality_score':None})
    if seen!=expected:raise ValueError('Missing question/method rows')
    output.mkdir(parents=True)
    with (output/'bounded_contexts.jsonl').open('w',encoding='utf-8') as stream:
        for row in result:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    plan=read_json(design);parent=canonical_hash(plan)
    plan['protocol_id']='review-comparison-design-v1.1'
    plan['controlled_track']['context_budget']['tokenizer_artifact']=tokenizer
    plan['controlled_track']['warning']='Only BM25/vector context packaging checked; remaining method adapters still need the same serializer/budget gate.'
    plan['blocking_conditions']=[b for b in plan['blocking_conditions'] if b!='common_tokenizer_not_locked']
    plan['parent_design_sha256']=parent
    atomic_json(output/'design_v1_1.json',plan)
    atomic_json(output/'tokenizer_manifest.json',tokenizer)
    atomic_json(output/'summary.json',{'n_contexts':len(result),'token_limit':2000,'largest_context_tokens':max(r['context_tokens'] for r in result),
        'empty_contexts':sum(not r['context'] for r in result),'input_retrieval_manifest_sha256':file_hash(retrieval/'manifest.json'),
        'actual_api_calls':0,'quality_scores_computed':False,'ready_for_paid_batch':False,
        'serializer_code_sha256':file_hash(Path(__file__)),
        'limitations':'Only two adapters checked on legacy source chunks; other methods, human gold and full released index remain missing.'})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('retrieval','design','cache','output'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args();run(**vars(args))
