"""Run one previously unreserved development task; never merge or approve it."""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src/extraction'))
from workflow_io import atomic_json, read_json, canonical_hash, file_hash, loads
from chunk_runner import contract, prompt_for
from task_plan import plan
from reextract_review import sections_from_document, Client, APIBlocked
from strict_runner import _key, SYSTEM
from chunk_contract import evaluate_bounded_task, scoped_task_schema


def ensure_unreserved(history, source_hash, task_hash):
    for path in history.rglob('request.json'):
        request = read_json(path)
        if request.get('source_sha256') == source_hash and request.get('task_sha256') == task_hash:
            raise ValueError('Task previously reserved; no automatic replay')


def run(source, task_id, history, output, keys_file, execute=False,ontology_profile='legacy-v3.1'):
    if output.exists():raise ValueError('Fresh output required')
    document = read_json(source)
    planned = plan(document)
    matches = [t for t in planned['tasks'] if t['task_id'] == task_id]
    if len(matches) != 1:raise ValueError('Unique planned task required')
    task = matches[0]; source_hash = file_hash(source); task_hash = canonical_hash(task)
    ensure_unreserved(history, source_hash, task_hash)
    policy, _ = contract(ontology_profile=ontology_profile)
    sections = sections_from_document(document)
    response_schema = scoped_task_schema(policy['schema'],task,planned['catalog'])
    prompt = prompt_for(task, planned['catalog'], sections, 12,ontology_profile)
    output.mkdir(parents=True)
    atomic_json(output/'task.json',task)
    atomic_json(output/'manifest.json',{'source_sha256':source_hash,'task_sha256':task_hash,
        'policy_sha256':canonical_hash(policy),'code_sha256':file_hash(Path(__file__)),
        'response_schema_sha256':canonical_hash(response_schema),
        'ontology_profile':ontology_profile,
        'protocol_id':policy['version'],
        'task_id':task_id,'model':'gemini-2.5-flash','max_api_calls':int(execute),
        'scope':'single development task, not full paper extraction', 'approved_for_graph':False})
    if not execute:
        atomic_json(output/'outcome.json',{'state':'preflight','api_attempts':0});return
    key = _key(argparse.Namespace(keys_file=keys_file))
    atomic_json(output/'request.json',{'source_sha256':source_hash,'task_sha256':task_hash,
        'task_id':task_id,'prompt':prompt,'prompt_sha256':canonical_hash(prompt),
        'policy_sha256':canonical_hash(policy),'api_call':True})
    client = Client(key, 'gemini-2.5-flash', 4, response_schema=response_schema, system_instruction=SYSTEM)
    try:
        text, raw, metadata = client.generate(prompt)
    except Exception as exc:
        http = re.fullmatch(r'Gemini HTTP (\d{3})',str(exc))
        outcome = {'state':'api_blocked' if isinstance(exc, APIBlocked) else 'failed_or_in_doubt',
                   'api_attempts':1,'http_status':int(http[1]) if http else None,
                   'status':exc.status if isinstance(exc,APIBlocked) else None,
                   'exception_type':type(exc).__name__,'automatic_retry':False,'usage':None}
        atomic_json(output/'outcome.json',outcome)
        print(outcome);return
    atomic_json(output/'response.json',{'text':text,'service_response':raw,'metadata':metadata})
    try:
        if metadata.get('finish_reason') != 'STOP':raise ValueError('Truncated response')
        cleaned, issues, blockers, continuation = evaluate_bounded_task(loads(text),task,planned['catalog'],sections,ontology_profile=ontology_profile)
        result = {'extraction_result':cleaned,'validation_issues':issues,'blocking_issues':blockers,
                  'continuation':continuation,'status':'quarantined' if issues else 'needs_continuation' if continuation else 'complete_task_pending_semantic_review',
                  'approved_for_graph':False,'full_paper_complete':False}
    except Exception as exc:
        result = {'status':'quarantined','exception_type':type(exc).__name__,'approved_for_graph':False,'full_paper_complete':False}
    result['ontology_profile']=ontology_profile
    result['protocol_id']=policy['version']
    atomic_json(output/'result.json',result)
    outcome = {'state':'response_received','task_status':result['status'],'api_attempts':1,
               'usage':metadata.get('usage'),'api_seconds':metadata.get('api_seconds'),
               'automatic_retry':False,'quality_score':None}
    atomic_json(output/'outcome.json',outcome)
    print(outcome)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','history','output','keys-file'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--task-id',required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--ontology-profile',default='legacy-v3.1',choices=['legacy-v3.1','composition-experimental-v1'])
    run(**vars(parser.parse_args()))
