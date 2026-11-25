"""Deterministic rejection of unsupported measurements; semantic review still required."""
import copy
import re
try:
    from .reextract_review import validate_extraction, normalize, SIGNATURES, ENTITY_TYPES
    from .semantic_triage import audit
except ImportError:
    from reextract_review import validate_extraction, normalize, SIGNATURES, ENTITY_TYPES
    from semantic_triage import audit

SCALAR=r'[+\-−]?(?:\d+(?:\.\d+)?|\.\d+)(?:\s*[eE]\s*[+\-−–]?\s*\d+)?'
VALUE=re.compile(rf'{SCALAR}(?:\s*(?:to|[-–—])\s*{SCALAR})?')
FIELDS=('endpoint','value','unit','object','condition','uncertainty','source_report')


def grounded(field,quotes,*,number=False,unit=False):
    target=normalize(field)
    if not target:return False
    if number:
        pattern=r'(?<![\w.])'+re.escape(target)+r'(?!\w|\.\d)'
    elif unit:
        # A unit may touch its numerical value (91.2%, 3.21mg/mL),
        # but must not be a suffix/prefix of another unit (g vs mg or g/mL).
        pattern=r'(?<![^\W\d])(?<![/^%])'+re.escape(target)+r'(?![\w/^%])'
    else:
        pattern=(r'(?<!\w)' if target[0].isalnum() else '')+re.escape(target)+(r'(?!\w|\.\d)' if target[-1].isalnum() else '')
    return any(re.search(pattern,normalize(quote)) is not None for quote in quotes)


def measurement_errors(entity,sections=None):
    value=entity.get('measurement')
    if not isinstance(value,dict) or set(value)!=set(FIELDS) or any(not isinstance(value[k],str) for k in FIELDS):
        return ['missing_or_invalid_measurement_fields']
    if any(len(v)>1000 for v in value.values()):return ['oversized_measurement']
    errors=[]
    evidence=entity.get('evidence',[])
    quotes=[e['text'] for e in evidence if isinstance(e,dict) and isinstance(e.get('text'),str)]
    scalar=normalize(value['value'])
    if not VALUE.fullmatch(scalar):errors.append('metric_requires_numeric_measured_value')
    elif not grounded(scalar,quotes,number=True):errors.append('measurement_value_not_in_evidence')
    for field in ('endpoint','object'):
        if not grounded(value[field],quotes):errors.append(field+'_not_in_evidence')
    for field in ('unit','condition'):
        if value[field] and not grounded(value[field],quotes,unit=field=='unit'):errors.append(field+'_not_in_evidence')
    if value['uncertainty'] and (not VALUE.fullmatch(normalize(value['uncertainty'])) or not grounded(value['uncertainty'],quotes,number=True)):
        errors.append('uncertainty_not_in_evidence')
    origin=value['source_report']
    if origin not in {'abstract','prose','table'}:errors.append('invalid_source_report')
    elif origin=='table' and not any(re.search(r'\bTable\s*\d',q,re.I) for q in quotes):
        errors.append('table_result_missing_table_context')
    elif origin=='abstract' and sections is not None:
        abstract={s['section_id'] for s in sections if s.get('kind')=='abstract'}
        own=[e['text'] for e in evidence if e.get('section_id') in abstract]
        if not grounded(scalar,own,number=True):errors.append('abstract_result_not_supported_by_abstract')
    return errors


def validate_strict(payload,sections,*,require_names=False,ontology_profile='legacy-v3.1'):
    accepted,issues=validate_extraction(payload,sections,require_names=require_names,ontology_profile=ontology_profile)
    entities=[]
    for entity in accepted['entities']:
        errors=measurement_errors(entity,sections) if entity['type']=='Metric' else ([] if 'measurement' not in entity else ['measurement_on_non_metric'])
        if errors:
            issues.append({'kind':'entity','reason':'invalid_measurement','details':errors,'item':entity})
        else:entities.append(entity)
    valid={e['id'] for e in entities}
    relations=[]
    for relation in accepted['relations']:
        if relation['source'] not in valid or relation['target'] not in valid:
            issues.append({'kind':'relation','reason':'endpoint_rejected_by_strict_validation','item':relation})
        else:relations.append(relation)
    cleaned={'entities':entities,'relations':relations}
    blockers=[]
    # Never silently merge aliases or resolve source disagreements.
    blockers.extend(issue for issue in audit(cleaned)['issues'] if issue.get('reason')!='metric_without_numeric_value')
    groups={}
    for entity in entities:
        if entity['type']!='Metric':continue
        m=entity['measurement']
        key=tuple(normalize(m[k]).casefold() for k in ('endpoint','object','condition'))
        signature=tuple(normalize(m[k]) for k in ('value','unit','uncertainty'))
        groups.setdefault(key,[]).append((entity['id'],signature))
    for key,items in groups.items():
        # Two reports may legitimately differ; keep both but require resolution/review.
        if len({signature for _,signature in items})>1:
            blockers.append({'reason':'conflicting_measurement_reports','measurement_key':key,'entity_ids':[name for name,_ in items]})
    return cleaned,issues,blockers


def strict_quote_schema(base):
    schema=copy.deepcopy(base)
    entity=schema['properties']['entities']['items']
    entity['properties']['name']={'type':'STRING'}
    entity['required']=list(dict.fromkeys(entity['required']+['name']))
    properties={field:{'type':'STRING'} for field in FIELDS}
    properties['source_report']['enum']=['abstract','prose','table']
    schema['properties']['entities']['items']['properties']['measurement']={
        'type':'OBJECT','properties':properties,'required':list(FIELDS)}
    return schema


def validate_graph_records(data):
    """Preflight the complete paper before opening a database transaction."""
    if not isinstance(data,dict) or not isinstance(data.get('filename'),str) or not data['filename'].strip():
        raise ValueError('A nonempty paper filename is required')
    if data.get('ontology_profile','legacy-v3.1')!='legacy-v3.1':
        raise ValueError('Experimental ontology requires an explicitly versioned experimental importer')
    payload=data.get('extraction_result')
    if not isinstance(payload,dict) or any(not isinstance(payload.get(k),list) for k in ('entities','relations')):
        raise ValueError('Invalid graph payload')
    types={}
    for entity in payload['entities']:
        if not isinstance(entity,dict) or not isinstance(entity.get('id'),str) or not entity['id'].strip() or entity.get('type') not in ENTITY_TYPES:
            raise ValueError('Invalid graph entity')
        name=entity.get('name',entity['id'])
        if data.get('protocol_id') in {'strict-extraction-v3.1','chunked-extraction-v3.1'} and 'name' not in entity:raise ValueError('Source name required under v3.1')
        if not isinstance(name,str) or not name.strip() or len(name)>2048:raise ValueError('Invalid source name')
        if len(entity['id'])>2048 or not isinstance(entity.get('description',''),str):raise ValueError('Invalid graph entity fields')
        if entity['id'] in types:raise ValueError('Duplicate or ambiguous graph entity identifier')
        types[entity['id']]=entity['type']
        if entity['type']=='Metric' and measurement_errors(entity):raise ValueError('Metric measurement failed preflight')
    seen=set()
    for relation in payload['relations']:
        if not isinstance(relation,dict) or any(not isinstance(relation.get(k),str) for k in ('source','target','type')):
            raise ValueError('Invalid graph relation')
        key=tuple(relation[k] for k in ('source','type','target'))
        if key in seen:raise ValueError('Duplicate graph relation')
        seen.add(key)
        signature=(types.get(relation['source']),types.get(relation['target']))
        if SIGNATURES.get(relation['type'])!=signature:raise ValueError('Missing endpoint or invalid graph relation signature')
    return payload
