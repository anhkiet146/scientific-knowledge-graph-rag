import argparse
import asyncio
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/evaluation')]
from workflow_io import read_json,loads,atomic_json,file_hash,canonical_hash
from snapshot_benchmark import generation_prompt
from budgeted_gemini_text import BudgetedText


async def run(contexts,keys_file,history,output,question_id=1,method='kg',execute=False):
    if output.exists():raise ValueError('Fresh output required; no retries')
    manifest=read_json(contexts.parent/'manifest.json')
    if file_hash(contexts)!=manifest['contexts_sha256']:raise ValueError('Context file changed')
    rows=[loads(s) for s in contexts.read_text(encoding='utf-8').split('\n') if s]
    chosen=[r for r in rows if r['question_id']==question_id and r['method']==method]
    if len(chosen)!=1:raise ValueError('Unique frozen case required')
    case=chosen[0]
    if canonical_hash(case['context_json'])!=case['context_sha256'] or loads(case['context_json'])!=case['context']:
        raise ValueError('Context integrity failure')
    if not case['context']:
        raise ValueError('No context: abstain locally; generation API must not be called')
    prompt=generation_prompt(case['question'],case['context'])
    for path in history.rglob('request.json'):
        request=read_json(path)
        old_prompt=request.get('prompt')
        for content in request.get('body',{}).get('contents',[]):
            for part in content.get('parts',[]):
                if part.get('text')==prompt:raise ValueError('Prompt previously reserved; do not retry')
        if old_prompt==prompt:raise ValueError('Prompt previously reserved; do not retry')
    key=read_json(keys_file).get('keys',{}).get('main')
    if not isinstance(key,str) or not key.strip():raise ValueError('Main credential required')
    output.mkdir(parents=True)
    atomic_json(output/'case.json',case)
    atomic_json(output/'prompt.json',{'prompt':prompt})
    code=[Path(__file__),ROOT/'src/evaluation/budgeted_gemini_text.py',ROOT/'src/evaluation/snapshot_benchmark.py']
    atomic_json(output/'manifest.json',{'contexts_sha256':file_hash(contexts),'context_sha256':case['context_sha256'],
        'question_id':question_id,'method':method,'credential_label':'main','model':'gemini-2.5-flash',
        'temperature':0,'thinking_budget':0,'max_output_tokens':1024,'max_api_attempts':int(execute),
        'automatic_retry':False,'scope':'Separate development task, not merged with old study; no independent grading',
        'code_sha256':{p.name:file_hash(p) for p in code}})
    snapshot=output/'code';snapshot.mkdir()
    for path in code:shutil.copy2(path,snapshot/path.name)
    if not execute:
        atomic_json(output/'summary.json',{'state':'preflight_only','actual_api_attempts':0});return
    provider=BudgetedText(key.strip(),output/'provider_journal',max_calls=1,max_output_tokens=1024)
    state='received'
    try:
        answer=await provider(prompt)
        atomic_json(output/'result.json',{'question_id':question_id,'method':method,'answer':answer,
            'context_sha256':case['context_sha256'],'quality_score':None,'assessment_source':None})
    except Exception:state='failed_or_in_doubt_no_retry'
    outcome=output/'provider_journal/0001/outcome.json'
    outcome=read_json(outcome) if outcome.exists() else {}
    atomic_json(output/'summary.json',{'state':state,'actual_api_attempts':provider.calls,
        'http_status':outcome.get('http_status'),'usage':outcome.get('usage'),
        'request_seconds':outcome.get('request_seconds'),'quality_scores_computed':False,'automatic_retry':False})
    print('Single diagnostic:',state,'attempts:',provider.calls,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for field in ('contexts','keys-file','history','output'):parser.add_argument('--'+field,type=Path,required=True)
    parser.add_argument('--question-id',type=int,default=1);parser.add_argument('--method',default='kg')
    parser.add_argument('--execute',action='store_true')
    asyncio.run(run(**vars(parser.parse_args())))
