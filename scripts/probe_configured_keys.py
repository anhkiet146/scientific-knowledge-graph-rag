import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from workflow_io import atomic_json,read_json,file_hash


def configured_keys(config):
    if not isinstance(config.get('keys'),dict):raise ValueError('Expected named keys mapping')
    unique={}
    for label,value in config['keys'].items():
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}',label):raise ValueError('Unsupported key label')
        if not isinstance(value,str) or not value.strip():raise ValueError('Empty or invalid credential entry')
        unique.setdefault(value.strip(),[]).append(label)
    if not 1<=len(unique)<=8:raise ValueError('Expected one to eight unique credentials')
    return list(unique.items())


def safe_error(raw):
    result={'quota_windows':[],'credential_reason':None}
    try:data=json.loads(raw.decode('utf-8'))
    except (ValueError,UnicodeError):return result
    error=data.get('error',{}) if isinstance(data,dict) else {}
    if not isinstance(error,dict):return result
    details=error.get('details',[])
    if not isinstance(details,list):return result
    windows=set()
    allowed={'API_KEY_INVALID','API_KEY_EXPIRED','API_KEY_SERVICE_BLOCKED','API_KEY_IP_ADDRESS_BLOCKED','API_KEY_HTTP_REFERRER_BLOCKED','SERVICE_DISABLED','CONSUMER_INVALID','BILLING_DISABLED'}
    for detail in details:
        if not isinstance(detail,dict):continue
        if detail.get('reason') in allowed:result['credential_reason']=detail['reason']
        violations=detail.get('violations',[])
        if not isinstance(violations,list):continue
        for violation in violations:
            if not isinstance(violation,dict):continue
            quota=str(violation.get('quotaId','')).lower()
            if 'perday' in quota:windows.add('per_day')
            if 'perminute' in quota:windows.add('per_minute')
    result['quota_windows']=sorted(windows)
    return result


def probe(key,model):
    body={'contents':[{'role':'user','parts':[{'text':'Reply with OK only.'}]}],
        'generationConfig':{'temperature':0,'maxOutputTokens':8,'thinkingConfig':{'thinkingBudget':0}}}
    request=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',
        data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':key})
    started=time.perf_counter()
    try:
        with urllib.request.urlopen(request,timeout=25) as response:
            raw=response.read(65537)
            if len(raw)>65536:return {'state':'response_too_large','http_status':response.status}
            data=json.loads(raw.decode('utf-8'))
            usage=data.get('usageMetadata',{})
            result={'state':'service_responded','http_status':response.status,
                'usable_short_response':any(c.get('finishReason')=='STOP' and any(p.get('text','').strip() for p in c.get('content',{}).get('parts',[]) if not p.get('thought')) for c in data.get('candidates',[])),
                'usage':{k:v for k,v in usage.items() if k in {'promptTokenCount','candidatesTokenCount','totalTokenCount','thoughtsTokenCount'} and type(v) is int}}
    except urllib.error.HTTPError as exc:
        result={'state':'http_error','http_status':exc.code,**safe_error(exc.read(16384))}
    except Exception as exc:
        result={'state':'transport_or_parse_in_doubt','http_status':None,'exception_type':type(exc).__name__}
    result['request_seconds']=time.perf_counter()-started
    result['utc_time']=datetime.now(timezone.utc).isoformat()
    return result


def run(keys_file,output,execute=False):
    if output.exists():raise ValueError('Fresh diagnostic output required; never resume or retry')
    keys=configured_keys(read_json(keys_file));output.mkdir(parents=True)
    atomic_json(output/'manifest.json',{'model':'gemini-2.5-flash','unique_keys':len(keys),'configured_entries':sum(len(names) for _,names in keys),
        'key_alias_groups':[names for _,names in keys],'execute':execute,'maximum_attempts':len(keys) if execute else 0,
        'prompt':'Reply with OK only.','max_output_tokens':8,'automatic_retries':0,
        'purpose':'Credential diagnostics only; no benchmark calls or quota bypass. A successful probe does not establish full-run quota.',
        'code_sha256':file_hash(Path(__file__))})
    results=[]
    if execute:
        for index,(key,labels) in enumerate(keys,1):
            folder=output/f'{index:02d}';folder.mkdir()
            atomic_json(folder/'reservation.json',{'aliases':labels,'state':'reserved_before_call','automatic_retry':False})
            result={'aliases':labels,**probe(key,'gemini-2.5-flash')}
            atomic_json(folder/'result.json',result);results.append(result)
            atomic_json(output/'summary.json',{'actual_api_attempts':len(results),'results':results,'complete':len(results)==len(keys)})
            print(json.dumps(result),flush=True)
    else:atomic_json(output/'summary.json',{'actual_api_attempts':0,'state':'dry_run_only'})


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--keys-file',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--execute',action='store_true')
    run(**vars(p.parse_args()))
