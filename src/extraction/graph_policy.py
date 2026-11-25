"""Integrity-bound review attestation; not authentication or independent gold."""
import re
try:
    from .workflow_io import canonical_hash
    from .strict_validation import validate_graph_records
except ImportError:
    from workflow_io import canonical_hash
    from strict_validation import validate_graph_records


def review_hash(data):
    return canonical_hash({k:v for k,v in data.items() if k!='review'})


def require_graph_review(data):
    if data.get('protocol_id') in {'coordinate-table-evidence-v1','coordinate-measurement-candidates-v1',
        'coordinate-table-bundle-v1','coordinate-table-pilot-v1'}:
        raise ValueError('Coordinate evidence needs a reviewed graph adapter; direct import is disabled')
    if data.get('protocol_id')=='chunked-extraction-v3.1':
        coverage=data.get('execution_coverage',{})
        if not isinstance(coverage,dict):raise ValueError('Complete task coverage required before graph review')
        roots=coverage.get('root_tasks');done=coverage.get('completed_tasks');receipts=coverage.get('task_receipt_sha256')
        if (coverage.get('complete') is not True or coverage.get('pending_tasks')!=[]
            or coverage.get('failed_tasks')!=[] or not isinstance(roots,list) or not roots
            or not isinstance(done,list) or any(not isinstance(t,str) for t in roots+done)
            or len(set(done))!=len(done) or not set(roots).issubset(done)
            or not isinstance(receipts,dict) or set(receipts)!=set(done)
            or any(not isinstance(h,str) or not re.fullmatch(r'[a-f0-9]{64}',h) for h in receipts.values())
            or not isinstance(coverage.get('plan_sha256'),str)
            or not re.fullmatch(r'[a-f0-9]{64}',coverage['plan_sha256'])):
            raise ValueError('Complete task coverage required before graph review')
    payload=validate_graph_records(data)
    if not payload['entities']:raise ValueError('Empty extraction cannot enter the graph')
    source=data.get('source_sha256')
    if not isinstance(source,str) or not re.fullmatch(r'[a-f0-9]{64}',source):
        raise ValueError('Source checksum required before graph import')
    if data.get('candidate_status')=='quarantined' or data.get('validation_issues'):
        raise ValueError('Quarantined or unresolved records cannot enter the graph')
    review=data.get('review')
    if (not isinstance(review,dict) or review.get('decision')!='approved'
        or not isinstance(review.get('reviewer'),str) or not review['reviewer'].strip()
        or not isinstance(review.get('notes'),str) or not review['notes'].strip()
        or review.get('payload_sha256')!=review_hash(data)):
        raise ValueError('Matching review attestation required; model output is not approval')
    acknowledgements=review.get('acknowledged_issues',[])
    if not isinstance(acknowledgements,list):raise ValueError('Invalid issue acknowledgements')
    for issue in data.get('blocking_issues',[]):
        allowed=({'retain_source_conflict'} if issue.get('reason')=='conflicting_measurement_reports'
                 else {'confirmed_distinct_entities'} if issue.get('kind')=='alias_candidate'
                 else {'confirmed_digital_dataset'} if issue.get('reason') in {'possible_biological_object_as_dataset','target_requires_dataset_review'}
                 else set())
        matched=[a for a in acknowledgements if isinstance(a,dict) and a.get('issue_sha256')==canonical_hash(issue)
                 and a.get('disposition') in allowed
                 and isinstance(a.get('notes'),str) and a['notes'].strip()]
        if not matched:raise ValueError('Unacknowledged source conflict or semantic flag')
    for record in payload['entities']+payload['relations']:
        evidence=record.get('evidence')
        if (not isinstance(evidence,list) or not evidence or len(evidence)>16
            or any(not isinstance(e,dict) or not isinstance(e.get('text'),str) or len(e['text'].strip())<8
                   or '\ufffd' in e['text'] or not isinstance(e.get('section_id'),str) or not e['section_id'] for e in evidence)):
            raise ValueError('Valid evidence required for every imported entity/relation')
    return payload
