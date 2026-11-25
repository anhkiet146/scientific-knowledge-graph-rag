"""Provider-injected study runner. No built-in network client and no paid CLI.

    A reserved job with no durable response is in doubt, never retried. A saved
    response is recoverable offline without another provider call. Resume binds
    exact contexts, prompts, code and sampling configuration. One coordinator.
"""
import asyncio
from pathlib import Path
import sys
import time
import re
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/retrieval')]
from workflow_io import atomic_json,read_json,file_hash,canonical_hash
from snapshot_benchmark import generation_prompt
from controlled_generation_pilot import BASE_METHODS,parse_verdict
from verifier_policies import verifier_policy


def local_abstention(question):
    return ('Không đủ bằng chứng trong ngữ cảnh được cung cấp.'
            if re.search(r'[ăâđêôơưĂÂĐÊÔƠƯ\u1ea0-\u1ef9]',question)
            else 'Insufficient evidence in the supplied context.')


async def run_study(contexts,output,provider=None,max_calls=0,repeats=5,base_methods=None,verification_policy='v2'):
    if type(max_calls) is not int or max_calls<0 or type(repeats) is not int or not 1<=repeats<=5:
        raise ValueError('Invalid budget or repeats')
    verifier_prompt,verifier_filter=verifier_policy(verification_policy)
    bykey={}
    for row in contexts:
        key=(row['question_id'],row['method'])
        if key in bykey:raise ValueError('Duplicate context')
        if row['context_sha256']!=canonical_hash(row['context_json']):raise ValueError('Context hash mismatch')
        import json
        if json.loads(row['context_json'])!=row['context'] or not 0<=row['context_tokens']<=2000:raise ValueError('Invalid context serialization/budget')
        bykey[key]=row
    selected_methods=tuple(BASE_METHODS if base_methods is None else base_methods)
    if not selected_methods or any(not isinstance(m,str) or not re.fullmatch(r'[a-z][a-z0-9_]*',m) for m in selected_methods) or len(set(selected_methods))!=len(selected_methods) or 'kg' not in selected_methods or 'kg_verified' in selected_methods:
        raise ValueError('Invalid generation method list')
    qids=sorted({q for q,_ in bykey});methods=(*selected_methods,'kg_verified')
    if not qids or set(bykey)!={(q,m) for q in qids for m in methods}:raise ValueError('Incomplete grid')
    for q in qids:
        if len({bykey[q,m]['question'] for m in methods})!=1:raise ValueError('Question mismatch')
        if bykey[q,'kg']['context_json']!=bykey[q,'kg_verified']['context_json']:raise ValueError('Pairing mismatch')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    contract={'context_hash':canonical_hash(contexts),'repeats':repeats,'questions':qids,'methods':list(methods),
              'verification_policy':verification_policy,
              'generator_settings':{'model':'gemini-2.5-flash','temperature':0,'thinking_budget':0,'answer_tokens':1024,'verifier_tokens':4096},
              'code':{p.name:file_hash(p) for p in [Path(__file__),Path(__file__).with_name('snapshot_benchmark.py'),
                       Path(__file__).with_name('controlled_generation_pilot.py'),
                       *[ROOT/'src/retrieval'/name for name in ['claim_verification.py','claim_verification_experimental.py',
                           'claim_verification_literal.py','verifier_policies.py']]]}}
    plan=output/'contract.json'
    if plan.exists():
        if read_json(plan)!=contract:raise ValueError('Resume contract changed')
    else:atomic_json(plan,contract)
    # Exclusive process lock; stale locks require inspection, never auto-removal.
    lock=output/'coordinator.lock'
    with lock.open('x') as stream:stream.write('Single coordinator; inspect journal before removing stale lock.')
    calls=0;complete=0;stop=None
    try:
        import random
        for repeat in range(1,repeats+1):
            questions=qids.copy();random.Random(20261115+repeat).shuffle(questions)
            for q in questions:
                order=list(selected_methods);random.Random(20261115+100*repeat+q).shuffle(order)
                for method in order+['kg_verified']:
                    folder=output/'jobs'/f'q{q}_r{repeat}_{method}';folder.mkdir(parents=True,exist_ok=True)
                    row=bykey[q,method];verified=method=='kg_verified'
                    draft=None
                    if verified:
                        draft=read_json(output/'jobs'/f'q{q}_r{repeat}_kg'/'result.json')['answer']
                    prompt=verifier_prompt(row['question'],draft,row['context']) if verified else generation_prompt(row['question'],row['context'])
                    request={'prompt':prompt,'output_token_limit':4096 if verified else 1024,'json_mode':verified}
                    request_hash=canonical_hash(request)
                    result_file=folder/'result.json';request_file=folder/'request.json';response_file=folder/'response.json'
                    if request_file.exists() and read_json(request_file)!=request:raise ValueError('Saved request changed')
                    if result_file.exists():
                        saved=read_json(result_file)
                        if not request_file.exists() or not response_file.exists() or saved['request_hash']!=request_hash or saved['response_hash']!=file_hash(response_file):raise ValueError('Saved result binding invalid')
                        if saved['result_hash']!=canonical_hash({k:v for k,v in saved.items() if k!='result_hash'}):raise ValueError('Saved result modified')
                        complete+=1;continue
                    if not response_file.exists():
                        if request_file.exists():stop='in_doubt_request_no_automatic_retry';break
                        if not row['context']:
                            atomic_json(request_file,request)
                            atomic_json(response_file,{'text':draft if verified else local_abstention(row['question']),
                                'request_hash':request_hash,'provider_adapter_seconds':0,'origin':'local_empty_context_abstention'})
                        elif provider is None or calls>=max_calls:stop='budget_or_provider_unavailable';break
                        # Persist reservation BEFORE invoking the provider. Failed and
                        # cancelled calls consume an attempt, even without a response.
                        if not response_file.exists():
                            atomic_json(request_file,request);calls+=1;started=time.perf_counter()
                            try:
                                text=await provider(prompt,output_token_limit=request['output_token_limit'],json_mode=verified)
                                if not isinstance(text,str) or not text.strip():raise ValueError('Empty provider response')
                                atomic_json(response_file,{'text':text,'request_hash':request_hash,'provider_adapter_seconds':time.perf_counter()-started})
                            except Exception:
                                atomic_json(folder/'failure.json',{'state':'failed_or_in_doubt','automatic_retry':False})
                                stop='provider_failure_or_in_doubt';break
                    response=read_json(response_file)
                    if response['request_hash']!=request_hash:raise ValueError('Response binding invalid')
                    text=response['text']
                    if response.get('origin')=='local_empty_context_abstention':
                        answer=text;audit={'state':'local_empty_context_abstention'}
                    elif verified:
                        verdict,_=parse_verdict(text);answer,audit=verifier_filter(draft,row['context'],verdict)
                    else:answer=text;audit=None
                    result={'question_id':q,'repeat':repeat,'method':method,'answer':answer,'claim_audit':audit,
                            'answer_origin':response.get('origin','provider'),
                            'request_hash':request_hash,'response_hash':file_hash(response_file),'quality_score':None}
                    result['result_hash']=canonical_hash(result);atomic_json(result_file,result);complete+=1
                if stop:break
            if stop:break
        summary={'state':stop or 'generation_complete_quality_pending','complete_records':complete,
                 'expected_records':len(qids)*repeats*len(methods),'new_provider_attempts':calls,'quality_scores_computed':False,
                 'limits':'Provider-injected API stage only. Retrieval/index times belong to separate artifacts; no end-to-end claim.'}
        atomic_json(output/'summary.json',summary);return summary
    finally:lock.unlink()
