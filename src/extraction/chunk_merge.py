"""Paper-local exact reconciliation; never match technical IDs across tasks."""
import copy
try:
    from .workflow_io import canonical_hash
    from .reextract_review import normalize
    from .strict_validation import validate_strict,FIELDS
except ImportError:
    from workflow_io import canonical_hash
    from reextract_review import normalize
    from strict_validation import validate_strict,FIELDS


def semantic_key(entity):
    if entity['type']=='Metric':
        return ('Metric',*(normalize(entity['measurement'][f]) for f in FIELDS))
    return (entity['type'],normalize(entity['name']))


def merge_tasks(task_results,sections,source_sha256,*,ontology_profile='legacy-v3.1'):
    entities={};id_keys={};local={};provenance={};issues=[];relations={}
    for task_id,payload in sorted(task_results.items()):
        for entity in payload['entities']:
            key=semantic_key(entity)
            new_id='e_'+canonical_hash([source_sha256,key])[:24]
            if new_id in id_keys and id_keys[new_id]!=key:raise ValueError('Canonical ID collision')
            id_keys[new_id]=key
            local_key=(task_id,entity['id'])
            if local_key in local:raise ValueError('Duplicate task-local entity ID')
            local[local_key]=new_id
            if key not in entities:
                entities[key]={**copy.deepcopy(entity),'id':new_id,'evidence':[]}
                provenance[new_id]={'task_local_ids':[],'descriptions':[]}
            record=entities[key]
            for evidence in entity['evidence']:
                if evidence not in record['evidence']:record['evidence'].append(copy.deepcopy(evidence))
            provenance[new_id]['task_local_ids'].append({'task_id':task_id,'local_id':entity['id']})
            if entity.get('description','') not in provenance[new_id]['descriptions']:
                provenance[new_id]['descriptions'].append(entity.get('description',''))
    for task_id,payload in sorted(task_results.items()):
        for relation in payload['relations']:
            src=local.get((task_id,relation['source']));tgt=local.get((task_id,relation['target']))
            if src is None or tgt is None:
                issues.append({'reason':'unresolved_task_local_endpoint','task_id':task_id,'item':relation});continue
            key=(src,relation['type'],tgt)
            if key not in relations:relations[key]={'source':src,'type':relation['type'],'target':tgt,'evidence':[]}
            for evidence in relation['evidence']:
                if evidence not in relations[key]['evidence']:relations[key]['evidence'].append(copy.deepcopy(evidence))
    combined={'entities':list(entities.values()),'relations':list(relations.values())}
    # Keep every raw task result; do not silently drop citations to fit the limit.
    for kind in ('entities','relations'):
        for record in combined[kind]:
            if len(record['evidence'])>16:
                issues.append({'reason':'merged_evidence_requires_curation','kind':kind,'item':record})
    accepted,rejected,blockers=validate_strict(combined,sections,require_names=True,ontology_profile=ontology_profile)
    return accepted,issues+rejected,blockers,provenance
