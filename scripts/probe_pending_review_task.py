import argparse
import asyncio
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/evaluation')]
from workflow_io import read_json,loads,atomic_json,canonical_hash,file_hash
from controlled_generation_pilot import BASE_METHODS
from snapshot_benchmark import generation_prompt
from budgeted_gemini_text import BudgetedText
from strict_runner import _key


def previous_probe_tasks(parent):
    binding=file_hash(parent/'contract.json');tasks=set();limited=False
    for path in parent.parent.glob('*/manifest.json'):
        record=read_json(path)
        if record.get('parent_contract_sha256')!=binding:continue
        task=record.get('task',{})
        if {'question_id','repeat','method'}<=task.keys():tasks.add((task['question_id'],task['repeat'],task['method']))
        summary=path.parent/'summary.json'
        if summary.exists() and read_json(summary).get('http_status')==429:limited=True
    return tasks,limited


async def run(args):
    if args.output.exists():raise ValueError('Fresh output required')
    rows=[loads(s) for s in args.contexts.read_text(encoding='utf-8').split('\n') if s]
    contract=read_json(args.parent/'contract.json')
    if canonical_hash(rows)!=contract['context_hash']:raise ValueError('Contexts differ from parent')
    done=sorted((args.parent/'jobs').glob('*/result.json'))
    if not done:raise ValueError('Parent pilot needs completed record')
    first=read_json(done[0]);qid=first['question_id'];repeat=first['repeat']
    attempted,limited=previous_probe_tasks(args.parent)
    if limited:raise ValueError('Previous probe returned HTTP 429; inspect provider quota before any further probe')
    method=next((m for m in BASE_METHODS if (qid,repeat,m) not in attempted and not (args.parent/'jobs'/f'q{qid}_r{repeat}_{m}'/'request.json').exists()),None)
    if not method:raise ValueError('No unattempted base method')
    case=next(r for r in rows if r['question_id']==qid and r['method']==method)
    prompt=generation_prompt(case['question'],case['context'])
    for path in (args.parent/'provider_segments').glob('*/*/request.json'):
        if read_json(path)['body']['contents'][-1]['parts'][0]['text']==prompt:raise ValueError('Would repeat a previous request')
    args.output.mkdir(parents=True)
    atomic_json(args.output/'case.json',case)
    atomic_json(args.output/'manifest.json',{'parent_contract_sha256':file_hash(args.parent/'contract.json'),
        'contexts_sha256':file_hash(args.contexts),'task':{'question_id':qid,'repeat':repeat,'method':method},
        'max_api_calls':1,'scope':'New unattempted task only, separate diagnostic; parent in-doubt request unchanged',
        'code_sha256':file_hash(Path(__file__)),'adapter_sha256':file_hash(ROOT/'src/evaluation/budgeted_gemini_text.py')})
    provider=BudgetedText(_key(args),args.output/'provider_journal',max_calls=1,max_output_tokens=1024)
    state='received'
    try:
        answer=await provider(prompt)
        atomic_json(args.output/'result.json',{'question_id':qid,'repeat':repeat,'method':method,'answer':answer,
            'context_sha256':case['context_sha256'],'quality_score':None,'status':'separate_probe_not_merged_into_parent'})
    except Exception:state='failed_or_in_doubt_no_retry'
    outcome_file=args.output/'provider_journal/0001/outcome.json'
    outcome=read_json(outcome_file) if outcome_file.exists() else {}
    summary={'status':state,'reserved_attempts':provider.calls,'http_status':outcome.get('http_status'),
        'exception_type':outcome.get('exception_type'),'completed_records':int((args.output/'result.json').exists()),
        'retry_performed':False,'parent_modified':False,'quality_scores_computed':False}
    atomic_json(args.output/'summary.json',summary);print(summary)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for flag in ('contexts','parent','output','keys-file'):p.add_argument('--'+flag,type=Path,required=True)
    asyncio.run(run(p.parse_args()))
