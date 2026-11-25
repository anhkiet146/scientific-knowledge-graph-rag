"""Separate GPT judge run on frozen cases; no Gemini scores are reused."""
import argparse
import ast
import datetime
import json
import os
import re
from pathlib import Path
import shutil
import sys
import time
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from regrade_legacy_qa import prepare,validate
from workflow_io import read_json,loads,atomic_json,file_hash,canonical_hash


def credentials(config):
    values={}
    for node in ast.parse(config.read_text(encoding='utf-8-sig')).body:
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id in ('OPENAI_API_KEY','OPENAI_JUDGE_MODEL'):
                    try:values[target.id]=ast.literal_eval(node.value)
                    except (ValueError,TypeError):pass
    key=values.get('OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY','')
    model=values.get('OPENAI_JUDGE_MODEL')
    if not isinstance(key,str) or not key.strip() or not isinstance(model,str) or not model.startswith('gpt-'):
        raise ValueError('Valid OpenAI credential and explicit GPT model required')
    return key,model


def body_for(prompt,model):
    return {'model':model,'input':prompt,'store':False,'max_output_tokens':4096,
        'reasoning':{'effort':'low'},'text':{'format':{'type':'json_object'}}}


def response_text(raw):
    if raw.get('status')!='completed':raise ValueError('Incomplete GPT response')
    chunks=[c['text'] for item in raw.get('output',[]) if item.get('type')=='message'
        for c in item.get('content',[]) if c.get('type')=='output_text']
    text=''.join(chunks)
    if not text.strip():raise ValueError('Missing GPT output text')
    return text


def http_call(body,key):
    request=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(body).encode(),
        headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
    with urllib.request.urlopen(request,timeout=180) as response:
        raw=response.read(16*1024*1024+1)
        if len(raw)>16*1024*1024:raise ValueError('Oversized GPT response')
        return loads(raw.decode('utf-8'))


def safe_error(exc):
    code=None;diagnostics={}
    if isinstance(exc,urllib.error.HTTPError):
        try:
            body=exc.read(64000).decode('utf-8',errors='replace')
            diagnostics['body_mentions_quota']='quota' in body.lower()
            diagnostics['body_mentions_rate_limit']=any(x in body.lower() for x in ('rate limit','rate_limit'))
            diagnostics['body_mentions_billing']='billing' in body.lower()
            retry=exc.headers.get('Retry-After') if exc.headers else None
            if isinstance(retry,str) and re.fullmatch(r'\d{1,6}',retry):diagnostics['retry_after_seconds']=int(retry)
            value=loads(body);candidate=value.get('error',{}).get('code')
            if candidate in {'invalid_api_key','insufficient_quota','rate_limit_exceeded','model_not_found',
                'unsupported_parameter','invalid_value','billing_hard_limit_reached'}:code=candidate
        except Exception:pass
    return {'exception_type':type(exc).__name__,'http_status':getattr(exc,'code',None),
        'provider_error_code':code,'automatic_retry':False,**diagnostics}


def run(prior,output,config,max_calls,transport=http_call):
    if output.exists():raise ValueError('Fresh GPT run required')
    if type(max_calls) is not int or not 1<=max_calls<=135:raise ValueError('Budget 1..135 required')
    m=read_json(prior/'manifest.json');source=ROOT.parents[1]/'outputs/review_revision/legacy_audit/comparison_results_recovered.jsonl'
    if file_hash(source)!=m['source_sha256']:raise ValueError('Historical source changed')
    rows=[loads(s) for s in source.read_text(encoding='utf-8').split('\n') if s]
    by_id={(r['method'],r['question_id']):r for r in rows};cases=[]
    for p in sorted((prior/'cases').glob('*.json')):
        case=read_json(p);row=by_id[case['method'],case['question_id']];prompt,context=prepare(row)
        if (prompt,context,canonical_hash(row))!=(case['prompt'],case['context'],case['source_row_sha256']):
            raise ValueError('Frozen case changed')
        cases.append(case)
    if len(cases)!=135 or {c['case_id'] for c in cases}!=set(range(1,136)):raise ValueError('Complete case grid required')
    key,model=credentials(config);output.mkdir(parents=True)
    snapshot=output/'policy_snapshot';snapshot.mkdir()
    for p in (Path(__file__),ROOT/'scripts/regrade_legacy_qa.py'):shutil.copy2(p,snapshot/p.name)
    atomic_json(output/'manifest.json',{'provider':'OpenAI Responses API','requested_model':model,
        'max_api_calls':max_calls,'reasoning_effort':'low','temperature':'omitted; provider default, not claimed as zero',
        'max_output_tokens':4096,'store':False,'response_format':'json_object','automatic_retry':False,
        'source_sha256':file_hash(source),'prior_case_hashes':{p.name:file_hash(p) for p in (prior/'cases').glob('*.json')},
        'code_sha256':file_hash(Path(__file__)),'rubric_code_sha256':file_hash(ROOT/'scripts/regrade_legacy_qa.py'),
        'same_rubric_as_gemini':True,'gemini_grades_reused':False,
        'limits':'AI proxy judge, not independent experts. Project-internal references; unequal historical context representations; missing context metrics null. Does not repair historical provenance or complete a new fair QA experiment.'})
    completed=0;attempts=0;stop=None
    for case in cases[:max_calls]:
        folder=output/'provider_journal'/f"{case['case_id']:03}";folder.mkdir(parents=True)
        body=body_for(case['prompt'],model)
        atomic_json(folder/'request.json',{'case_id':case['case_id'],'body':body,'body_sha256':canonical_hash(body)})
        attempts+=1;started=time.perf_counter()
        try:
            raw=transport(body,key);atomic_json(folder/'response.json',raw)
            grade=validate(response_text(raw),case['context'])
            if not isinstance(raw.get('model'),str) or not raw['model']:raise ValueError('Returned model identity absent')
        except Exception as exc:
            error=safe_error(exc);error['request_seconds']=time.perf_counter()-started;atomic_json(folder/'outcome.json',error)
            stop='provider_or_validation_failure';break
        atomic_json(folder/'outcome.json',{'state':'received_and_validated','returned_model':raw['model'],
            'usage':raw.get('usage'),'request_seconds':time.perf_counter()-started})
        atomic_json(output/'grades'/f"{case['case_id']:03}.json",{'case_id':case['case_id'],
            'question_id':case['question_id'],'method':case['method'],'grade':grade,
            'judge_model':raw['model'],'prompt_sha256':canonical_hash(case['prompt']),
            'response_sha256':file_hash(folder/'response.json'),'label':'GPT AI proxy regrade',
            'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
        completed+=1;print('GPT grades saved:',completed,'of135',flush=True)
        atomic_json(output/'checkpoint.json',{'completed':completed,'api_attempts':attempts})
        time.sleep(1)
    atomic_json(output/'summary.json',{'state':stop or ('grading_complete' if completed==135 else 'budget_reached'),
        'completed':completed,'expected':135,'api_attempts':attempts,'gemini_scores_mixed':False,
        'independent_human_grading':False,'quality_comparison_complete':False})
    print(stop or 'finished',completed,'GPT grades',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for flag in ('prior','output','config'):p.add_argument('--'+flag,type=Path,required=True)
    p.add_argument('--max-calls',type=int,required=True);a=p.parse_args();run(a.prior,a.output,a.config,a.max_calls)
