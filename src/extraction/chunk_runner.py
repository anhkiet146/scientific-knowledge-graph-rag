"""Source-bound task execution and paper reconciliation. No automatic approval."""
import argparse
import copy
import json
import re
try:
    from .ontology_profiles import schema_for_profile,relation_instructions,signatures
except ImportError:
    from ontology_profiles import schema_for_profile,relation_instructions,signatures
from pathlib import Path
try:
    from . import strict_runner as single
    from .task_plan import plan
    from .chunk_contract import task_schema,evaluate_bounded_task,scoped_task_schema
    from .chunk_merge import merge_tasks
    from .reextract_review import Client,APIBlocked,sections_from_document
    from .source_quality import quality_report
    from .workflow_io import atomic_json,read_json,loads,canonical_hash,file_hash,RunLock
except ImportError:
    import strict_runner as single
    from task_plan import plan
    from chunk_contract import task_schema,evaluate_bounded_task,scoped_task_schema
    from chunk_merge import merge_tasks
    from reextract_review import Client,APIBlocked,sections_from_document
    from source_quality import quality_report
    from workflow_io import atomic_json,read_json,loads,canonical_hash,file_hash,RunLock

VERSION='chunked-extraction-v3.1'
PROMPT=Path(__file__).resolve().parents[2]/'prompts/chunked_extraction_v3_1.md'


def contract(max_items=100,max_depth=3,max_metrics=12,ontology_profile='legacy-v3.1'):
    base,files=single.policy()
    extras=[Path(__file__).with_name(n) for n in ('chunk_runner.py','chunk_contract.py','chunk_merge.py','task_plan.py')]
    version=VERSION if ontology_profile=='legacy-v3.1' else 'chunked-extraction-v3.2-experimental'
    value={**base,'version':version,'schema':schema_for_profile(task_schema(base['schema']),ontology_profile),
           'ontology_profile':ontology_profile,'relation_signatures':signatures(ontology_profile),
           'chunk_prompt_sha256':file_hash(PROMPT),'max_items':max_items,
           'max_continuation_depth':max_depth,'max_metrics_per_task':max_metrics,
           'code_sha256':{**base['code_sha256'],**{p.name:file_hash(p) for p in extras}}}
    return value,files+extras


def prompt_for(task,catalog,sections,max_metrics,ontology_profile='legacy-v3.1'):
    ids=set(task['scope_ids'])|set(task['context_ids'])
    section_ids={item['section_id'] for item in catalog['items'] if item['id'] in ids}
    source={'task_id':task['task_id'],'scope_ids':task['scope_ids'],'context_ids':task['context_ids'],
            'max_metric_records':max_metrics,'sections_sha256':catalog['sections_sha256'],
            'eligible_header_evidence_ids':[i['id'] for i in catalog['items'] if i['id'] in ids and i['kind']=='header'],
            'section_metadata':[{k:v for k,v in s.items() if k!='text'} for s in sections if s['section_id'] in section_ids],
            'evidence_catalog':[{k:i[k] for k in ('id','section_id','kind','text')} for i in catalog['items'] if i['id'] in ids]}
    template=PROMPT.read_text(encoding='utf-8')
    if template.count('{{RELATION_CONTRACT}}')!=1:raise ValueError('Relation contract template missing or duplicated')
    return template.replace('{{RELATION_CONTRACT}}',relation_instructions(ontology_profile))+'\nCURRENT TASK:\n'+json.dumps(source,ensure_ascii=False)


def _immutable(path,value):
    if path.exists():
        if canonical_hash(read_json(path))!=canonical_hash(value):raise ValueError('Immutable artifact changed: '+path.name)
    else:atomic_json(path,value)


def verify_task(folder):
    receipt=read_json(folder/'receipt.json')
    for filename,key in [('spec.json','spec_sha256'),('request.json','request_sha256'),
                         ('response.json','response_sha256'),('result.json','result_sha256')]:
        p=folder/filename
        if not p.exists() or file_hash(p)!=receipt.get(key):raise ValueError('Task artifact hash mismatch')
    return read_json(folder/'result.json')


def verify_budget_ledger(output,policy_hash):
    entries=sorted((output/'ledger').glob('*.json'))
    for number,path in enumerate(entries,1):
        entry=read_json(path)
        if entry.get('slot')!=number or path.name!=f'{number:08d}.json' or entry.get('policy_sha256')!=policy_hash:
            raise ValueError('API reservation ledger changed')
        relative=entry.get('request_path')
        if not isinstance(relative,str):raise ValueError('Invalid request path')
        request=(output/relative).resolve()
        if not request.is_relative_to((output/'tasks').resolve()) or not request.exists() or file_hash(request)!=entry.get('request_sha256'):
            raise ValueError('Reserved API request changed')
    return len(entries)


def run(args):
    source=args.input.resolve();output=args.output.resolve()
    if source==output or source.is_relative_to(output) or output.is_relative_to(source):raise ValueError('Separate non-nested input/output required')
    if args.limit<1 or args.max_api_calls<0 or args.max_tasks<0 or not 20<=args.max_items<=200:
        raise ValueError('Invalid task or budget limit')
    if not 0<=args.max_depth<=8 or not 1<=args.max_metrics<=40 or not 0<args.requests_per_minute<float('inf'):
        raise ValueError('Invalid generation settings')
    files=sorted(p for p in source.glob('*.json') if not p.name.startswith('_'))[:args.limit]
    if not files:raise ValueError('No sources')
    batch=getattr(args,'batch',False)
    if len(files)>2 and not batch:raise ValueError('More than two papers requires explicit --batch')
    profile=getattr(args,'ontology_profile','legacy-v3.1')
    if batch and profile!='legacy-v3.1':raise ValueError('Batch execution requires the default ontology')
    if batch and args.max_api_calls==0 and not args.preflight:
        raise ValueError('Batch execution requires an explicit positive API budget')
    policy,code_files=contract(args.max_items,args.max_depth,args.max_metrics,profile);policy_hash=canonical_hash(policy)
    manifest={'version':VERSION,'policy_sha256':policy_hash,'policy':policy,
              'execution_mode':'offline_fixture' if args.offline_responses else 'live',
              'requests_per_minute':args.requests_per_minute,
              'sources':[{'file':p.name,'sha256':file_hash(p),'paper_key':canonical_hash(p.name)[:20]} for p in files]}
    if batch:manifest['batch_execution']=True
    if args.offline_responses:
        manifest['fixtures']=[{'path':p.relative_to(args.offline_responses).as_posix(),'sha256':file_hash(p)}
                              for p in sorted(args.offline_responses.rglob('*.json'))]
    with RunLock(output):
        for name in ('sources','catalogs','plans','tasks','papers','ledger','policy_snapshot'):(output/name).mkdir(exist_ok=True)
        _immutable(output/'manifest.json',manifest)
        for p in code_files+[single.PROMPT_PATH,PROMPT]:
            dest=output/'policy_snapshot'/p.name
            if dest.exists() and file_hash(dest)!=file_hash(p):raise ValueError('Policy snapshot changed')
            if not dest.exists():dest.write_bytes(p.read_bytes())
        prepared=[]
        for path,entry in zip(files,manifest['sources']):
            snapshot=output/'sources'/path.name
            if not snapshot.exists():snapshot.write_bytes(path.read_bytes())
            if file_hash(snapshot)!=entry['sha256']:raise ValueError('Source snapshot changed')
            document=read_json(snapshot);planned=plan(document,args.max_items);sections=sections_from_document(document)
            _immutable(output/'catalogs'/path.name,planned['catalog']);_immutable(output/'plans'/path.name,planned)
            prepared.append((entry,document,sections,planned))
        reserved=verify_budget_ledger(output,policy_hash)
        for receipt in (output/'tasks').glob('*/*/receipt.json'):verify_task(receipt.parent)
        budget_path=output/'budget.json'
        if budget_path.exists():
            budget=read_json(budget_path)
            if budget['ceiling']!=args.max_api_calls:
                if not args.extend_budget or args.max_api_calls<max(budget['ceiling'],reserved):
                    raise ValueError('Budget changes require an explicit upward --extend-budget')
                budget['history'].append({'from':budget['ceiling'],'to':args.max_api_calls});budget['ceiling']=args.max_api_calls
                atomic_json(budget_path,budget)
        else:atomic_json(budget_path,{'ceiling':args.max_api_calls,'history':[]})
        if args.preflight:
            print(f'Chunk preflight: {len(files)} papers, {sum(len(p[3]["tasks"]) for p in prepared)} initial tasks; no API calls')
            return 0
        client=None;processed=0;stop=None;paper_summaries=[]
        for entry,document,sections,planned in prepared:
            catalog=planned['catalog'];queue=[{k:v for k,v in task.items() if k!='evidence'} for task in planned['tasks']]
            root_ids=[t['task_id'] for t in queue];seen=set();results={};task_issues=[];task_blockers=[];tasks_done=[];pending=[];failed=[];task_hashes={}
            while queue:
                task=queue.pop(0);task_id=task['task_id']
                if task_id in seen:raise ValueError('Duplicate task in continuation tree')
                seen.add(task_id)
                folder=output/'tasks'/entry['paper_key']/task_id;folder.mkdir(parents=True,exist_ok=True)
                _immutable(folder/'spec.json',task)
                prompt=prompt_for(task,catalog,sections,args.max_metrics,profile)
                response_schema=scoped_task_schema(policy['schema'],task,catalog)
                if (folder/'receipt.json').exists():
                    result=verify_task(folder)
                    request=read_json(folder/'request.json')
                    if request.get('prompt_sha256')!=canonical_hash(prompt) or request.get('policy_sha256')!=policy_hash:raise ValueError('Task request changed')
                else:
                    if stop or (args.max_tasks and processed>=args.max_tasks) or (output/'STOP').exists():
                        stop=stop or 'invocation_stopped';pending.append(task_id);continue
                    request_file=folder/'request.json';response_file=folder/'response.json'
                    if request_file.exists() and not response_file.exists():
                        failure=read_json(folder/'failure.json') if (folder/'failure.json').exists() else {}
                        if not (getattr(args,'retry_rejected',False) and failure.get('state')=='api_blocked'):
                            raise RuntimeError('In-doubt reserved request has no response; an API rejection needs explicit --retry-rejected, other outcomes require inspection')
                    request={'task_sha256':canonical_hash(task),'policy_sha256':policy_hash,'prompt':prompt,'prompt_sha256':canonical_hash(prompt),
                             'api_call':not bool(args.offline_responses),'source_sha256':entry['sha256'],
                             'response_schema_sha256':canonical_hash(response_schema)}
                    _immutable(request_file,request) if request_file.exists() else None
                    if not response_file.exists():
                        if not args.offline_responses and reserved>=args.max_api_calls:
                            stop='api_budget_exhausted';pending.append(task_id);continue
                        if not args.offline_responses and client is None:
                            client=Client(single._key(args),'gemini-2.5-flash',args.requests_per_minute,
                                          response_schema=policy['schema'],system_instruction=single.SYSTEM)
                        _immutable(request_file,request)
                        if args.offline_responses:
                            fixture=read_json(args.offline_responses/entry['paper_key']/(task_id+'.json'))
                            response={'text':fixture['text'],'metadata':{'finish_reason':fixture.get('finish_reason','STOP'),'execution_mode':'offline_fixture'},'service_response':None}
                        else:
                            reserved+=1
                            atomic_json(output/'ledger'/f'{reserved:08d}.json',{'slot':reserved,'policy_sha256':policy_hash,
                                'request_path':request_file.relative_to(output).as_posix(),'request_sha256':file_hash(request_file)})
                            try:
                                client.response_schema=response_schema
                                text,raw,metadata=client.generate(prompt);response={'text':text,'metadata':metadata,'service_response':raw}
                            except APIBlocked as exc:
                                failure={'state':'api_blocked','status':exc.status,'slot':reserved,'automatic_retry':False,
                                         'service_error':exc.detail}
                                atomic_json(folder/'failure.json',failure)
                                atomic_json(folder/'rejections'/f'{reserved:08d}.json',failure)
                                atomic_json(output/'progress.json',{'state':'api_blocked','reserved_call_slots':reserved,'status':exc.status});return 3
                            except Exception as exc:
                                http = re.fullmatch(r'Gemini HTTP (\d{3})', str(exc))
                                atomic_json(folder/'failure.json', {'state':'failed_or_in_doubt',
                                    'exception_type':type(exc).__name__,
                                    'http_status':int(http[1]) if http else None,
                                    'automatic_retry':False})
                                atomic_json(output/'progress.json', {'state':'failed_or_in_doubt',
                                    'reserved_call_slots':reserved,'failed_task':task_id,
                                    'automatic_retry':False})
                                raise RuntimeError('Task request outcome unknown; no automatic retry') from None
                        atomic_json(response_file,response)
                    response=read_json(response_file);child=None
                    try:
                        if response['metadata'].get('finish_reason')!='STOP':raise ValueError('Truncated task response')
                        payload=loads(response['text'])
                        cleaned,issues,blockers,child=evaluate_bounded_task(payload,task,catalog,sections,args.max_depth,args.max_metrics,ontology_profile=profile)
                        if issues:child=None
                    except (ValueError,TypeError,KeyError,AttributeError) as exc:
                        cleaned={'entities':[],'relations':[]};issues=[{'reason':'invalid_task_response','error':str(exc)}];blockers=[];child=None
                    result={'task_id':task_id,'extraction_result':cleaned,'validation_issues':issues,'blocking_issues':blockers,
                            'continuation':child,'status':'quarantined' if issues else 'needs_continuation' if child else 'complete'}
                    atomic_json(folder/'result.json',result)
                    atomic_json(folder/'receipt.json',{'spec_sha256':file_hash(folder/'spec.json'),'request_sha256':file_hash(request_file),
                        'response_sha256':file_hash(response_file),'result_sha256':file_hash(folder/'result.json')})
                    processed+=1
                task_hashes[task_id]=file_hash(folder/'receipt.json');tasks_done.append(task_id)
                results[task_id]=result['extraction_result']
                task_issues.extend({'task_id':task_id,**issue} for issue in result['validation_issues'])
                task_blockers.extend({'task_id':task_id,**issue} for issue in result['blocking_issues'])
                if result['status']=='quarantined':failed.append(task_id)
                if result['continuation']:queue.append(result['continuation'])
            merged,merge_issues,blockers,provenance=merge_tasks(results,sections,entry['sha256'],ontology_profile=profile)
            complete=not pending and not failed and all(root in tasks_done for root in root_ids)
            issues=task_issues+merge_issues
            if complete and not merged['entities']:issues.append({'reason':'empty_paper_extraction'})
            status='quarantined' if issues else 'pending_semantic_review' if complete else 'incomplete'
            coverage={'root_tasks':root_ids,'completed_tasks':tasks_done,'pending_tasks':pending,'failed_tasks':failed,
                      'complete':complete,'plan_sha256':canonical_hash(planned),'task_receipt_sha256':task_hashes,
                      'meaning':'execution coverage only, not proof that every scientific fact was extracted'}
            candidate={'filename':entry['file'],'paper_title':document.get('title',document.get('paper_title','')),
                       'protocol_id':policy['version'],'ontology_profile':profile,'execution_mode':manifest['execution_mode'],'source_sha256':entry['sha256'],
                       'policy_sha256':policy_hash,'candidate_status':status,'extraction_result':merged,'validation_issues':issues,
                       'blocking_issues':task_blockers+blockers,'execution_coverage':coverage,'merge_provenance':provenance,
                       'source_quality':quality_report(document),'semantic_accuracy_established':False}
            candidate_path=output/'papers'/(entry['paper_key']+'.json')
            if candidate_path.exists():
                previous=read_json(candidate_path)
                if 'review' in previous:
                    if canonical_hash({k:v for k,v in previous.items() if k!='review'})!=canonical_hash(candidate):
                        raise ValueError('Reviewed candidate would change; use a new output directory')
                    candidate=previous
            atomic_json(candidate_path,candidate)
            paper_summaries.append({'file':entry['file'],'candidate_status':status,'execution_complete':complete,
                                    'completed_tasks':len(tasks_done),'pending_tasks':len(pending),'failed_tasks':len(failed)})
        final_state=(stop or 'incomplete') if any(p['pending_tasks'] for p in paper_summaries) else (
            'validation_failed' if any(p['candidate_status']=='quarantined' for p in paper_summaries) else 'candidates_ready_for_review')
        atomic_json(output/'progress.json',{'state':final_state,'reserved_call_slots':reserved,
            'execution_mode':manifest['execution_mode'],'papers':paper_summaries,'approved_for_graph':0})
        return 2 if any(p['candidate_status']=='quarantined' for p in paper_summaries) else 3 if any(not p['execution_complete'] for p in paper_summaries) else 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=2);parser.add_argument('--max-items',type=int,default=100)
    parser.add_argument('--max-depth',type=int,default=3);parser.add_argument('--max-metrics',type=int,default=12)
    parser.add_argument('--max-api-calls',type=int,default=2);parser.add_argument('--extend-budget',action='store_true')
    parser.add_argument('--max-tasks',type=int,default=0);parser.add_argument('--requests-per-minute',type=float,default=4)
    parser.add_argument('--keys-file',type=Path);parser.add_argument('--offline-responses',type=Path)
    parser.add_argument('--preflight',action='store_true')
    parser.add_argument('--batch',action='store_true')
    parser.add_argument('--retry-rejected',action='store_true')
    parser.add_argument('--ontology-profile',default='legacy-v3.1',choices=['legacy-v3.1','composition-experimental-v1'])
    return run(parser.parse_args())


if __name__=='__main__':raise SystemExit(main())
