"""Execute only unattempted second case after first advisory validation failure."""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src/evaluation'),str(ROOT/'src/extraction')]
from pilot_llm_normalization import validate
from budgeted_gemini_text import BudgetedText
from strict_runner import _key
from workflow_io import read_json,atomic_json,file_hash,loads

async def run(folder,keys):
    summary=read_json(folder/'summary.json');manifest=read_json(folder/'manifest.json')
    if summary['reserved_api_calls']!=1 or summary['status']!='provider_or_validation_failure_no_retry':raise ValueError('Not the expected single-attempt pilot')
    if file_hash(folder/'cases.json')!=manifest['cases_sha256']:raise ValueError('Cases changed')
    if len(list((folder/'provider_journal').glob('*/request.json')))!=1:raise ValueError('Unexpected previous calls')
    cases=read_json(folder/'cases.json');case=cases[1]
    first_prompt=read_json(folder/'alias-1_prompt.json')['prompt'];prefix=first_prompt.split('\n',1)[0]
    prompt=prefix+'\n'+json.dumps(case,ensure_ascii=False)
    provider=BudgetedText(_key(SimpleNamespace(keys_file=keys)),folder/'second_case_journal',max_calls=1,max_output_tokens=1536)
    atomic_json(folder/'alias-2_prompt.json',{'prompt':prompt,'case_sha256':file_hash(folder/'cases.json'),'continuation':'Unattempted second case only; never resend first'})
    state='received';result=None
    try:
        response=await provider(prompt,json_mode=True)
        try:result=validate(loads(response),case)
        except ValueError as exc:
            state='validation_failed';atomic_json(folder/'alias-2_validation.json',{'state':state,'reason':str(exc),'auto_merge':False})
        if result:atomic_json(folder/'alias-2_proposal.json',result)
    except Exception:state='provider_failure_or_in_doubt'
    atomic_json(folder/'combined_summary.json',{'first_case_status':summary['status'],'second_case_status':state,
        'reserved_api_calls':1+provider.calls,'second_case_decision':result['decision'] if result else None,
        'validated_proposals':int(result is not None),'graph_merges_applied':0,'quality_scores_computed':False})
    print(state,result['decision'] if result else '')

if __name__=='__main__':
    if len(sys.argv)!=3:raise ValueError('pilot_directory keys_file required')
    asyncio.run(run(Path(sys.argv[1]),Path(sys.argv[2])))
