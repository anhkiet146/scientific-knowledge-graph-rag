"""Bounded one-question/two-repeat frozen-context pilot, not a full QA benchmark."""
import argparse
import asyncio
import json
from pathlib import Path
import random
import re
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/retrieval')]
from workflow_io import read_json,loads,file_hash,atomic_json,canonical_hash
from strict_runner import _key
from snapshot_benchmark import generation_prompt
from claim_verification import verification_prompt,filter_claims,verification_prompt_v2,filter_claims_v2
from verifier_policies import POLICIES,verifier_policy
from budgeted_gemini_text import BudgetedText

BASE_METHODS=('bm25','vector','kg','kg_no_expansion','kg_raw','kg_no_semantic','kg_no_relation')


def parse_verdict(text):
    stripped=text.strip();wrapped=False
    match=re.fullmatch(r'```(?:json)?\s*\n(.*?)\n```',stripped,flags=re.S)
    if match:stripped=match[1];wrapped=True
    verdict=loads(stripped)
    if not isinstance(verdict,dict) or set(verdict)!={'claims'} or not isinstance(verdict['claims'],list):raise ValueError('Invalid claim-verification response')
    return verdict,wrapped


def load_contexts(path,question_id):
    chosen={}
    for line in path.read_text(encoding='utf-8').split('\n'):
        if not line:continue
        row=loads(line)
        if row['question_id']!=question_id:continue
        method=row['method']
        if method in chosen:raise ValueError('Duplicate selected question/method')
        if row['context_sha256']!=canonical_hash(row['context_json']) or json.loads(row['context_json'])!=row['context']:
            raise ValueError('Context checksum mismatch')
        if row['context_tokens']>2000:raise ValueError('Context budget exceeded')
        chosen[method]=row
    if set(chosen)!=set(BASE_METHODS)|{'kg_verified'}:raise ValueError('All eight frozen methods required')
    if len({r['question'] for r in chosen.values()})!=1:raise ValueError('Methods have different questions')
    if chosen['kg']['context_json']!=chosen['kg_verified']['context_json']:raise ValueError('Paired verification requires identical KG context')
    return chosen


async def run(args):
    verifier_version=getattr(args,'verifier_version','v1')
    prompt_verifier,apply_verifier=verifier_policy(verifier_version)
    if args.resume_partial and verifier_version!='v1':raise ValueError('Cannot resume v1 experiment with a changed verifier')
    if args.output.exists():raise ValueError('Fresh pilot output required; no automatic paid replay')
    if args.question_id<1 or not 1<=args.repeats<=2 or not 0<=args.max_api_calls<=16:raise ValueError('One question and at most two repeats/16 calls allowed')
    contexts=load_contexts(args.contexts,args.question_id)
    expected_calls=args.repeats*8
    prior_calls=0;inherited=[];first_repeat=1
    if args.resume_partial:
        old=read_json(args.resume_partial/'manifest.json')
        responses=sorted((args.resume_partial/'provider_journal').glob('*/response.json'))
        if old['contexts_sha256']!=file_hash(args.contexts) or old['question_ids']!=[args.question_id] or args.repeats!=2 or len(responses)!=8:
            raise ValueError('Only the source-bound first-repeat/8-response partial pilot can be continued')
        prior_calls=8;first_repeat=2
        for method in BASE_METHODS:
            row=read_json(args.resume_partial/'records'/f'r1_{method}.json')
            if row['generation_status']!='success' or row['context_sha256']!=contexts[method]['context_sha256']:raise ValueError('Incomplete or mismatched inherited generation')
            inherited.append(row)
        raw=read_json(responses[-1]);text=''.join(p.get('text','') for p in raw['candidates'][0]['content']['parts'] if not p.get('thought'))
        verdict,wrapped=parse_verdict(text);draft=next(r for r in inherited if r['method']=='kg')
        answer,audit=filter_claims(draft['draft_answer'],contexts['kg']['context'],verdict)
        inherited.append({'method':'kg_verified','question_id':args.question_id,'repeat':1,'question':draft['question'],
            'generation_status':'success','verification_status':'success','assessment_source':None,'quality_score':None,
            'draft_answer':draft['draft_answer'],'generated_answer':answer,'claim_audit':audit,'paired_kg_record':'r1_kg.json',
            'context_sha256':draft['context_sha256'],'transport_wrapper_removed_read_only':wrapped,
            'inherited_verification_response_sha256':file_hash(responses[-1])})
    args.output.mkdir(parents=True)
    manifest={'protocol_id':'frozen-context-paired-verification-pilot-v1.1','question_ids':[args.question_id],
        'methods':list(BASE_METHODS)+['kg_verified'],'repeats':args.repeats,'expected_calls_without_errors':expected_calls,
        'max_api_calls':args.max_api_calls,'mode':'live' if args.execute else 'preflight','contexts_sha256':file_hash(args.contexts),
        'generator':'gemini-2.5-flash','temperature':0,'max_output_tokens':1024,'verification_max_output_tokens':4096,'thinking_budget':0,
        'verification_pairing':'Reuse the exact KG draft; kg_verified does not generate a separate draft',
        'prior_api_calls':prior_calls,'prior_manifest_sha256':file_hash(args.resume_partial/'manifest.json') if args.resume_partial else None,
        'verifier_version':verifier_version,
        'verification_transport':'JSON object, optionally enclosed in one exact Markdown json fence; never repair JSON contents',
        'latency_scope':'Provider request and intentional throttle separately; precomputed retrieval excluded, no end-to-end claim',
        'limitations':'One known internal question, two repeats maximum; no SOTA full-corpus index, unseen evaluation, independent labels or confirmatory statistics',
        'code_sha256':{p.name:file_hash(p) for p in [Path(__file__),Path(__file__).with_name('budgeted_gemini_text.py'),
            ROOT/'src/retrieval/claim_verification.py',ROOT/'src/retrieval/claim_verification_experimental.py',
            ROOT/'src/retrieval/claim_verification_literal.py',ROOT/'src/retrieval/verifier_policies.py',
            Path(__file__).with_name('snapshot_benchmark.py')]}}
    atomic_json(args.output/'manifest.json',manifest)
    atomic_json(args.output/'selected_contexts.json',contexts)
    for method in BASE_METHODS:
        atomic_json(args.output/'prompts'/(method+'.json'),{'prompt':generation_prompt(contexts[method]['question'],contexts[method]['context'])})
    if not args.execute:
        atomic_json(args.output/'summary.json',{'status':'preflight_only','actual_api_calls':0,'expected_calls_without_errors':expected_calls});return
    if args.max_api_calls<expected_calls:raise ValueError('Budget must cover declared pilot before any request')
    provider=BudgetedText(_key(args),args.output/'provider_journal',max_calls=args.max_api_calls-prior_calls,
        scope='controlled_generation_pilot',max_output_tokens=1024,requests_per_minute=4)
    rows=list(inherited);stop=None
    for row in inherited:atomic_json(args.output/'records'/f"r{row['repeat']}_{row['method']}.json",row)
    for repeat in range(first_repeat,args.repeats+1):
        order=list(BASE_METHODS);random.Random(20261115+repeat).shuffle(order);draft=None
        for method in order:
            row={'method':method,'question_id':args.question_id,'repeat':repeat,'question':contexts[method]['question'],
                'context_sha256':contexts[method]['context_sha256'],'generation_status':'failed','assessment_source':None,'quality_score':None}
            started=time.perf_counter();before=provider.calls
            try:
                answer=await provider(generation_prompt(row['question'],contexts[method]['context']))
                row.update(generation_status='success',draft_answer=answer,generated_answer=answer,provider_call=provider.calls)
                if method=='kg':draft=row
            except Exception as exc:
                row['error']=str(exc).replace(provider.key,'[REDACTED]');stop='provider_failure';
            row['attempt_seconds_including_throttle']=time.perf_counter()-started
            if provider.calls>before:row['provider_outcome']=read_json(args.output/'provider_journal'/f'{provider.calls:04d}'/'outcome.json') if (args.output/'provider_journal'/f'{provider.calls:04d}'/'outcome.json').exists() else {'state':'response_not_accepted'}
            rows.append(row);atomic_json(args.output/'records'/f'r{repeat}_{method}.json',row)
            print('repeat',repeat,method,row['generation_status'],flush=True)
            if stop:break
        if stop:break
        if draft is None:raise ValueError('Missing KG draft for paired verification')
        row={'method':'kg_verified','question_id':args.question_id,'repeat':repeat,'question':draft['question'],
            'generation_status':'success','verification_status':'failed','assessment_source':None,'quality_score':None,
            'draft_answer':draft['draft_answer'],'paired_kg_record':f'r{repeat}_kg.json','context_sha256':draft['context_sha256']}
        started=time.perf_counter()
        try:
            text=await provider(prompt_verifier(row['question'],row['draft_answer'],contexts['kg']['context']),output_token_limit=4096,json_mode=True)
            verdict,wrapped=parse_verdict(text)
            answer,audit=apply_verifier(row['draft_answer'],contexts['kg']['context'],verdict)
            row.update(verification_status='success',generated_answer=answer,claim_audit=audit,provider_call=provider.calls,transport_wrapper_removed_read_only=wrapped)
        except Exception as exc:
            row['error']=str(exc).replace(provider.key,'[REDACTED]');stop='verification_failure'
        row['verification_seconds_including_throttle']=time.perf_counter()-started
        rows.append(row);atomic_json(args.output/'records'/f'r{repeat}_kg_verified.json',row)
        if stop:break
    atomic_json(args.output/'summary.json',{'status':stop or 'pilot_complete','reserved_api_calls':provider.calls+prior_calls,
        'current_run_calls':provider.calls,'prior_calls':prior_calls,
        'record_count':len(rows),'expected_record_count':args.repeats*8,'generation_success_rows':sum(r['generation_status']=='success' for r in rows),
        'verification_success_rows':sum(r.get('verification_status')=='success' for r in rows),'quality_scores_computed':False,
        'ready_for_confirmatory_reporting':False,'production_graph_writes':0})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contexts',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--question-id',type=int,default=1);parser.add_argument('--repeats',type=int,default=2)
    parser.add_argument('--max-api-calls',type=int,default=0);parser.add_argument('--keys-file',type=Path)
    parser.add_argument('--resume-partial',type=Path)
    parser.add_argument('--verifier-version',choices=list(POLICIES),default='v1')
    parser.add_argument('--execute',action='store_true');asyncio.run(run(parser.parse_args()))
