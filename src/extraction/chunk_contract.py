"""Task scope and explicit continuation contracts, independent of networking."""
import copy
try:
    from .workflow_io import canonical_hash
    from .strict_runner import evaluate
except ImportError:
    from workflow_io import canonical_hash
    from strict_runner import evaluate


def task_schema(base):
    schema=copy.deepcopy(base)
    schema['properties']['completion']={'type':'OBJECT','properties':{
        'status':{'type':'STRING','enum':['complete','needs_continuation']},
        'remaining_scope_ids':{'type':'ARRAY','items':{'type':'STRING'}}},
        'required':['status','remaining_scope_ids']}
    schema['required']=['entities','relations','completion']
    return schema


def scoped_task_schema(base,task,catalog):
    schema=copy.deepcopy(base)
    allowed=set(task['scope_ids'])|set(task['context_ids'])
    known={item['id'] for item in catalog['items']}
    if not task['scope_ids'] or not allowed<=known:
        raise ValueError('Task evidence scope must exist in catalog')
    for kind in ('entities','relations'):
        evidence=schema['properties'][kind]['items']['properties']['evidence_ids']
        evidence['items']['enum']=sorted(allowed)
        evidence['maxItems']=16
    schema['properties']['completion']['properties']['remaining_scope_ids']['items']['enum']=list(task['scope_ids'])
    return schema


def continuation(task,remaining,max_depth):
    if not isinstance(remaining,list) or not remaining or any(not isinstance(i,str) for i in remaining):
        raise ValueError('Nonempty remaining scope IDs required')
    if len(set(remaining))!=len(remaining) or not set(remaining)<set(task['scope_ids']):
        raise ValueError('Continuation must make strict progress within the parent scope')
    if task.get('depth',0)>=max_depth:raise ValueError('Continuation depth limit reached')
    ordered=[i for i in task['scope_ids'] if i in set(remaining)]
    context=list(dict.fromkeys(task['context_ids']+[i for i in task['scope_ids'] if i not in set(remaining)]))
    return {'task_id':task['task_id']+'__c_'+canonical_hash(ordered)[:12],
            'parent_task_id':task['task_id'],'scope_ids':ordered,'context_ids':context,
            'depth':task.get('depth',0)+1,'purpose':'Finish only remaining source scope; do not repeat completed findings'}


def evaluate_task(payload,task,catalog,sections,max_depth=3,*,ontology_profile='legacy-v3.1'):
    if not isinstance(payload,dict) or set(payload)!={'entities','relations','completion'}:
        raise ValueError('Task output requires entities, relations and completion only')
    completion=payload['completion']
    if not isinstance(completion,dict) or set(completion)!={'status','remaining_scope_ids'}:
        raise ValueError('Invalid task completion metadata')
    status=completion['status'];remaining=completion['remaining_scope_ids']
    if not isinstance(remaining,list):raise ValueError('Remaining scope must be an array')
    child=None
    if status=='complete':
        if remaining:raise ValueError('Complete task cannot have remaining scope')
    elif status=='needs_continuation':child=continuation(task,remaining,max_depth)
    else:raise ValueError('Unknown completion status')
    allowed=set(task['scope_ids'])|set(task['context_ids'])
    selected={**catalog,'items':[i for i in catalog['items'] if i['id'] in allowed]}
    transport={'entities':payload['entities'],'relations':payload['relations']}
    cleaned,issues,blockers=evaluate(transport,selected,sections,ontology_profile=ontology_profile)
    # Empty reference-only chunks can be valid; a whole empty paper cannot.
    issues=[i for i in issues if i.get('reason')!='empty_extraction']
    scope=set(task['scope_ids'])
    rejected_metric_ids=set()
    rejected_relation_keys=set()
    for entity in payload['entities']:
        if isinstance(entity,dict) and entity.get('type')=='Metric' and not scope.intersection(entity.get('evidence_ids',[])):
            issues.append({'reason':'measurement_outside_task_scope','item':entity})
            rejected_metric_ids.add(entity['id'])
    for relation in payload['relations']:
        if isinstance(relation,dict) and relation.get('type')!='AFFILIATED_WITH' and not scope.intersection(relation.get('evidence_ids',[])):
            issues.append({'reason':'relation_outside_task_scope','item':relation})
            rejected_relation_keys.add((relation['source'],relation['type'],relation['target']))
    cleaned['entities']=[e for e in cleaned['entities'] if e['id'] not in rejected_metric_ids]
    cleaned['relations']=[r for r in cleaned['relations']
        if (r['source'],r['type'],r['target']) not in rejected_relation_keys
        and r['source'] not in rejected_metric_ids and r['target'] not in rejected_metric_ids]
    return cleaned,issues,blockers,child


def evaluate_bounded_task(payload,task,catalog,sections,max_depth=3,max_metrics=12,*,ontology_profile='legacy-v3.1'):
    """An output overrun quarantines the task, but preserves validated records.

    Finish reason and JSON size are checked before this function. The metric
    target is a task compliance limit, not grounds to discard an intact response.
    """
    cleaned,issues,blockers,child=evaluate_task(payload,task,catalog,sections,max_depth,ontology_profile=ontology_profile)
    count=sum(e.get('type')=='Metric' for e in payload['entities'])
    if count>max_metrics:
        issues.append({'reason':'metric_output_limit_exceeded','count':count,'limit':max_metrics})
        child=None
    return cleaned,issues,blockers,child
