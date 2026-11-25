"""Plain-text Gemini adapter for released baselines, with no retries or schema rewrite."""
import asyncio
from pathlib import Path
import urllib.error
import urllib.request
import json
import time
import re
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src/extraction'))
from workflow_io import atomic_json,canonical_hash,loads


class BudgetedText:
    def __init__(self,key,output,max_calls=2,model='gemini-2.5-flash',transport=None,
                 scope='development',max_output_tokens=8192,requests_per_minute=None):
        if not isinstance(key,str) or not key.strip():raise ValueError('Valid key required')
        ceilings={'development':2,'controlled_generation_pilot':16,'review_generation':2025,'review_judging':135}
        if scope not in ceilings:raise ValueError('Unknown provider scope')
        ceiling=ceilings[scope]
        if type(max_calls) is not int or not 0<=max_calls<=ceiling:raise ValueError('API budget exceeds scope ceiling')
        if type(max_output_tokens) is not int or not 1<=max_output_tokens<=8192:raise ValueError('Invalid output limit')
        if requests_per_minute is not None and not 0<requests_per_minute<=60:raise ValueError('Invalid request rate')
        self.key=key;self.output=Path(output);self.maximum=max_calls;self.model=model
        self.output.mkdir(parents=True,exist_ok=True)
        if any(self.output.iterdir()):raise ValueError('Fresh provider journal required; in-doubt calls are never retried')
        self.calls=0;self.lock=asyncio.Lock();self.transport=transport or self._http
        self.output_tokens=max_output_tokens;self.interval=60/requests_per_minute if requests_per_minute else 0;self.next_request=0

    def _http(self,body):
        request=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+self.model+':generateContent',
            data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':self.key})
        try:
            with urllib.request.urlopen(request,timeout=180) as response:
                raw=response.read(16*1024*1024+1)
                if len(raw)>16*1024*1024:raise ValueError('Oversized service response')
                return loads(raw.decode())
        except urllib.error.HTTPError as exc:
            # Do not put provider error bodies or credentials in logs.
            raise RuntimeError('Gemini HTTP '+str(exc.code)+'; no automatic retry') from None

    async def __call__(self,prompt,system_prompt=None,history_messages=None,**kwargs):
        if not isinstance(prompt,str) or (system_prompt is not None and not isinstance(system_prompt,str)):
            raise ValueError('String prompts required')
        contents=[]
        for message in history_messages or []:
            role=message.get('role');content=message.get('content')
            if role not in {'user','assistant','model'} or not isinstance(content,str):raise ValueError('Unsupported history role')
            contents.append({'role':'model' if role=='assistant' else role,'parts':[{'text':content}]})
        contents.append({'role':'user','parts':[{'text':prompt}]})
        output_limit=kwargs.pop('output_token_limit',self.output_tokens)
        if type(output_limit) is not int or not 1<=output_limit<=8192:raise ValueError('Invalid call output limit')
        body={'contents':contents,'generationConfig':{'temperature':0,'maxOutputTokens':output_limit,'thinkingConfig':{'thinkingBudget':0}}}
        if kwargs.pop('json_mode',False):body['generationConfig']['responseMimeType']='application/json'
        if system_prompt:body['systemInstruction']={'parts':[{'text':system_prompt}]}
        async with self.lock:
            if self.calls>=self.maximum:raise RuntimeError('Released-baseline development API budget exhausted')
            wait=max(0,self.next_request-time.perf_counter())
            if wait:await asyncio.sleep(wait)
            self.next_request=time.perf_counter()+self.interval
            self.calls+=1;folder=self.output/f'{self.calls:04d}';folder.mkdir()
            atomic_json(folder/'request.json',{'model':self.model,'body':body,'body_sha256':canonical_hash(body),'throttle_wait_seconds':wait})
            started=time.perf_counter()
            try:raw=await asyncio.to_thread(self.transport,body)
            except Exception as exc:
                status=re.fullmatch(r'Gemini HTTP (\d{3}); no automatic retry',str(exc))
                atomic_json(folder/'outcome.json',{'state':'failed_or_in_doubt','no_automatic_retry':True,
                    'request_seconds':time.perf_counter()-started,'exception_type':type(exc).__name__,
                    'http_status':int(status[1]) if status else None})
                raise RuntimeError('Provider call failed or outcome unknown; inspect journal, do not retry') from None
            atomic_json(folder/'response.json',raw)
            candidates=raw.get('candidates',[])
            if len(candidates)!=1 or candidates[0].get('finishReason')!='STOP':raise ValueError('Missing or truncated provider output')
            text=''.join(p.get('text','') for p in candidates[0].get('content',{}).get('parts',[]) if not p.get('thought'))
            if not text.strip():raise ValueError('Empty provider text')
            atomic_json(folder/'outcome.json',{'state':'received','finish_reason':'STOP','usage':raw.get('usageMetadata',{}),
                'request_seconds':time.perf_counter()-started,'throttle_wait_seconds':wait})
            return text
