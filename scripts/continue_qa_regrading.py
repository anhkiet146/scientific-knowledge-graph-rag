"""Continue frozen QA grading with explicitly authorized backup credentials."""
import argparse
import asyncio
import datetime
from pathlib import Path
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from regrade_legacy_qa import prepare,validate
from workflow_io import read_json,atomic_json,file_hash,canonical_hash
from budgeted_gemini_text import BudgetedText


def load_previous(prior):
    manifest=read_json(prior/'manifest.json')
    if any(manifest.get(k)!=v for k,v in {'cases':135,'model':'gemini-2.5-flash',
        'temperature':0,'thinking_budget':0,'max_output_tokens':2048}.items()):
        raise ValueError('Previous judging contract differs')
    cases={}
    for path in sorted((prior/'cases').glob('*.json')):
        case=read_json(path);i=case['case_id']
        if type(i) is not int or i in cases:raise ValueError('Duplicate or invalid case ID')
        cases[i]=case
    if set(cases)!=set(range(1,136)):raise ValueError('135 frozen cases required')
    grades={}
    for path in sorted((prior/'grades').glob('*.json')):
        grade=read_json(path);i=grade['case_id'];case=cases[i]
        if i in grades or grade['prompt_sha256']!=canonical_hash(case['prompt']):raise ValueError('Saved grading binding differs')
        if any(grade[k]!=case[k] for k in ('method','question_id')):raise ValueError('Saved grading identity differs')
        import json
        validate(json.dumps(grade['grade']),case['context'])
        grades[i]=grade
    return manifest,cases,grades


async def run(prior,output,keys_file,max_calls,exclude_aliases=()):
    if output.exists():raise ValueError('Fresh continuation output required')
    if type(max_calls) is not int or not 1<=max_calls<=135:raise ValueError('Budget 1..135 required')
    manifest,cases,grades=load_previous(prior)
    # Reconstruct every prompt from the frozen source, rather than trusting an edited case file.
    source=ROOT.parents[1]/'outputs/review_revision/legacy_audit/comparison_results_recovered.jsonl'
    if file_hash(source)!=manifest['source_sha256']:raise ValueError('Historical source changed')
    from workflow_io import loads
    rows=[loads(s) for s in source.read_text(encoding='utf-8').split('\n') if s]
    by_identity={(r['method'],r['question_id']):r for r in rows}
    for case in cases.values():
        row=by_identity[case['method'],case['question_id']];prompt,context=prepare(row)
        if (prompt,context,canonical_hash(row))!=(case['prompt'],case['context'],case['source_row_sha256']):
            raise ValueError('Frozen source/prompt changed')
    credentials=read_json(keys_file);keys=credentials.get('keys',{});active=credentials.get('active')
    if not isinstance(keys,dict) or not isinstance(active,str):raise ValueError('Invalid credential selection')
    backups=[];seen=set()
    for alias,key in keys.items():
        if alias==active or alias in exclude_aliases or not isinstance(key,str) or not key.strip():continue
        digest=canonical_hash(key)
        if digest in seen:continue
        seen.add(digest);backups.append((alias,key))
    output.mkdir(parents=True)
    snapshot=output/'policy_snapshot';snapshot.mkdir()
    for p in (Path(__file__),ROOT/'scripts/regrade_legacy_qa.py',ROOT/'src/evaluation/budgeted_gemini_text.py'):
        shutil.copy2(p,snapshot/p.name)
    atomic_json(output/'manifest.json',{'prior':str(prior.resolve()),'prior_manifest_sha256':file_hash(prior/'manifest.json'),
        'source_sha256':manifest['source_sha256'],'model':manifest['model'],'max_new_api_calls':max_calls,
        'inherited_grades':len(grades),'backup_aliases':[a for a,_ in backups],
        'rotation':'Explicitly authorized; switch only after definite HTTP401/403/404/429 rejection, never unknown outcomes or invalid responses',
        'code_sha256':file_hash(Path(__file__)),'prior_case_hashes':{str(i):file_hash(prior/'cases'/f'{i:03}.json') for i in cases},
        'limits':manifest['limits']})
    attempts=0;statuses=[];stop=None
    pending=[i for i in sorted(cases) if i not in grades]
    for number,(alias,key) in enumerate(backups,1):
        if not pending or stop:break
        provider=BudgetedText(key,output/'provider_journals'/f'key_{number:02}',
            max_calls=min(135,max_calls-attempts),scope='review_judging',model=manifest['model'],
            max_output_tokens=2048,requests_per_minute=4)
        status={'alias':alias,'attempts':0,'completed':0,'http_status':None}
        statuses.append(status)
        for i in list(pending):
            if attempts>=max_calls:stop='budget_reached';break
            case=cases[i];attempts+=1;status['attempts']+=1
            atomic_json(output/'attempts'/f'{attempts:04}.json',{'case_id':i,'key_alias':alias,
                'prompt_sha256':canonical_hash(case['prompt']),'provider_journal':str(provider.output.resolve()),
                'provider_call':provider.calls+1})
            try:
                text=await provider(case['prompt'],json_mode=True)
                grade=validate(text,case['context'])
            except Exception as exc:
                folder=provider.output/f'{provider.calls:04}'
                outcome=read_json(folder/'outcome.json') if (folder/'outcome.json').exists() else {}
                status['http_status']=outcome.get('http_status')
                if status['http_status'] in (401,403,404,429) and not (folder/'response.json').exists():
                    status['state']='definite_provider_rejection';break
                status['state']='invalid_or_unknown_outcome';stop='manual_inspection_required'
                atomic_json(output/'failure.json',{'case_id':i,'exception_type':type(exc).__name__,
                    'automatic_retry':False});break
            saved={'case_id':i,'method':case['method'],'question_id':case['question_id'],'grade':grade,
                'prompt_sha256':canonical_hash(case['prompt']),'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'label':'AI proxy regrade','key_alias':alias}
            atomic_json(output/'grades'/f'{i:03}.json',saved);grades[i]=saved;pending.remove(i);status['completed']+=1
            print('Saved',len(grades),'of135 grades',flush=True)
        atomic_json(output/'checkpoint.json',{'complete_grades':len(grades),'new_api_attempts':attempts,'key_statuses':statuses})
        if attempts>=max_calls:stop='budget_reached'
    state='regrading_complete' if not pending else stop or 'all_backup_keys_rejected_or_unavailable'
    atomic_json(output/'combined_grades.json',{'grades':[grades[i] for i in sorted(grades)],
        'prior_grades_read_only':True,'incomplete':bool(pending)})
    atomic_json(output/'summary.json',{'state':state,'complete_grades':len(grades),'expected_grades':135,
        'remaining':len(pending),'new_api_attempts':attempts,'key_statuses':statuses,
        'grading_jobs_complete':not pending,'independent_human_grading':False,'quality_comparison_complete':False})
    print(state,len(grades),'grades total',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for flag in ('prior','output','keys-file'):p.add_argument('--'+flag,type=Path,required=True)
    p.add_argument('--max-calls',type=int,required=True)
    p.add_argument('--exclude-alias',action='append',default=[]);a=p.parse_args()
    asyncio.run(run(a.prior,a.output,a.keys_file,a.max_calls,a.exclude_alias))
