"""Verify real comparison artifacts before accessing credentials or generation."""
import argparse
import asyncio
import copy
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src/extraction'),str(ROOT/'src/evaluation')]
from workflow_io import read_json,atomic_json,file_hash,canonical_hash
from audit_fair_comparison import verified_contexts
from resumable_study import run_study
from budgeted_gemini_text import BudgetedText
from strict_runner import _key
from verifier_policies import POLICIES,verifier_policy


async def execute(protocol,bundles,output,encode,keys_file=None,max_calls=0,live=False,full_run=False,verification_policy='v2'):
    verifier_policy(verification_policy)
    if output.exists():raise ValueError('Fresh batch output required')
    settings=read_json(protocol);methods=read_json(bundles)
    if settings['generation']['shared_prompt_implementation_sha256']!=file_hash(ROOT/'src/evaluation/snapshot_benchmark.py'):
        raise ValueError('Shared generation prompt changed')
    required={'model':'gemini-2.5-flash','temperature':0,'thinking_budget':0,'max_output_tokens':1024,
              'references_in_prompt':False,'automatic_retry':False,'key_rotation':False}
    if any(settings['generation'].get(k)!=v for k,v in required.items()):raise ValueError('Unsupported shared generator settings')
    result,rows=verified_contexts(settings,methods,encode)
    output.mkdir(parents=True);atomic_json(output/'readiness.json',result)
    atomic_json(output/'manifest.json',{'protocol_sha256':file_hash(protocol),'bundles_sha256':file_hash(bundles),
        'code_sha256':file_hash(Path(__file__)),'artifact_checks':'real context hash, serialization, token count, question/query grid and corpus manifest',
        'context_methods':settings['context_methods'],'live_requested':live,'max_api_calls':max_calls,
        'latency_scope':'Generation stage on precomputed contexts; not end-to-end latency',
        'full_run':full_run,'verification_policy':verification_policy})
    if result['status']=='blocked':
        atomic_json(output/'summary.json',{'state':'blocked_before_credentials','api_attempts':0,'blocking_conditions':len(result['issues'])})
        return result
    if not live:
        atomic_json(output/'summary.json',{'state':'preflight_passed','api_attempts':0,'contexts':len(rows)})
        return result
    ceiling=16
    if full_run:
        if settings.get('question_count')!=45 or settings.get('repeats')!=5:
            raise ValueError('Full review run requires all45questions and five repeats')
        ceiling=45*5*(len(settings['context_methods'])+1)
        if ceiling>2025:raise ValueError('Full review protocol exceeds the declared2025-call ceiling')
    if type(max_calls) is not int or not 1<=max_calls<=ceiling:
        raise ValueError(f'Explicit API budget1..{ceiling} required')
    verified=[]
    for row in rows:
        if row['method']=='kg':
            paired=copy.deepcopy(row);paired['method']='kg_verified';verified.append(paired)
    rows.extend(verified)
    key=_key(argparse.Namespace(keys_file=keys_file))
    provider=BudgetedText(key,output/'provider_journal',max_calls=max_calls,
                          scope='review_generation' if full_run else 'controlled_generation_pilot',
                          model='gemini-2.5-flash',max_output_tokens=1024,requests_per_minute=4)
    return await run_study(rows,output/'study',provider,max_calls=max_calls,repeats=settings['repeats'],
                           base_methods=settings['context_methods'],verification_policy=verification_policy)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('protocol','bundles','output','tokenizer-cache'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--keys-file',type=Path);p.add_argument('--max-calls',type=int,default=0);p.add_argument('--live',action='store_true')
    p.add_argument('--full-run',action='store_true')
    p.add_argument('--verification-policy',choices=list(POLICIES),default='v2')
    a=p.parse_args();os.environ['TIKTOKEN_CACHE_DIR']=str(a.tokenizer_cache.resolve())
    import tiktoken,tiktoken.load
    def offline(url):raise RuntimeError('Tokenizer downloads disabled')
    tiktoken.load.read_file=offline;encoder=tiktoken.get_encoding('o200k_base')
    answer=asyncio.run(execute(a.protocol,a.bundles,a.output,lambda t:encoder.encode(t,disallowed_special=()),a.keys_file,a.max_calls,a.live,a.full_run,a.verification_policy))
    print(answer.get('status',answer.get('state')))
