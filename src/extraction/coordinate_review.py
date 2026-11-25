"""Bound development reviews. Validation is not reviewer authentication or gold."""
from pathlib import Path
try:
    from .workflow_io import read_json,canonical_hash,file_hash
    from .coordinate_runner import verified_bundle
except ImportError:
    from workflow_io import read_json,canonical_hash,file_hash
    from coordinate_runner import verified_bundle

FLAGS=('layout_correct','measurement_correct','footnote_and_reporting_note_checked')


def load_context(pilot):
    root=Path(pilot).resolve();manifest=read_json(root/'manifest.json');template=read_json(root/'review_template.json')
    if template['manifest_sha256']!=canonical_hash(manifest):raise ValueError('Review manifest mismatch')
    for name,digest in manifest['code_sha256'].items():
        if Path(name).name!=name or file_hash(root/'policy_snapshot'/name)!=digest:raise ValueError('Policy snapshot changed')
    candidates={};bundles={}
    for job in manifest['jobs']:
        key=job['id']
        if Path(key).name!=key or key in bundles:raise ValueError('Unsafe or duplicate job')
        paths={}
        for name,source in job['sources'].items():
            if name not in {'pdf','spec','evidence'}:raise ValueError('Unknown source role')
            path=root/'sources'/key/(name+Path(source['path']).suffix)
            if file_hash(path)!=source['sha256']:raise ValueError('Source snapshot changed')
            paths[name]=path
        bundle=read_json(root/'tables'/(key+'.json'));fresh=verified_bundle(**paths)
        fresh['input_sha256']={name:source['sha256'] for name,source in job['sources'].items()}
        if canonical_hash(bundle)!=canonical_hash(fresh):raise ValueError('Candidate differs from source replay')
        bundles[key]=bundle
        for row in bundle['measurements']['candidates']:
            if row['review_id'] in candidates:raise ValueError('Duplicate candidate ID')
            candidates[row['review_id']]=(key,row,bundle)
    expected={}
    for record in template['records']:
        rid=record['review_id']
        if rid in expected or rid not in candidates:raise ValueError('Unknown or duplicate template ID')
        key,row,bundle=candidates[rid]
        if (record['candidate_sha256']!=canonical_hash(row) or record['job_id']!=key
            or record['observation_id']!=row['observation_id']
            or record['source_pdf_sha256']!=bundle['table_evidence']['source_sha256']):
            raise ValueError('Template binding changed')
        expected[rid]=record
    if set(expected)!=set(candidates):raise ValueError('Template coverage mismatch')
    return template,candidates


def validate_submission(template,submission,*,blocked_ids=()):
    if not isinstance(submission,dict) or set(submission)!=set(template):raise ValueError('Review root fields changed')
    if any(submission[k]!=template[k] for k in template if k!='records'):raise ValueError('Review context changed')
    if not isinstance(submission['records'],list):raise ValueError('Review records required')
    expected={r['review_id']:r for r in template['records']};seen=set();counts={'unreviewed':0,'approved':0,'rejected':0,'needs_revision':0}
    for record in submission['records']:
        if not isinstance(record,dict):raise ValueError('Invalid review record')
        rid=record.get('review_id')
        if not isinstance(rid,str) or rid in seen or rid not in expected:raise ValueError('Unknown or duplicate review ID')
        seen.add(rid);base=expected[rid]
        if set(record)!=set(base) or any(record[k]!=base[k] for k in base if k!='review'):raise ValueError('Candidate binding changed')
        review=record['review']
        if not isinstance(review,dict) or set(review)!=set(base['review']):raise ValueError('Review fields changed')
        status=review['status']
        if not isinstance(status,str) or status not in counts:raise ValueError('Invalid review status')
        if any(not isinstance(review[k],str) or len(review[k])>10000 for k in ('reviewer','notes')):raise ValueError('Invalid reviewer or notes')
        if any(review[k] is not None and type(review[k]) is not bool for k in FLAGS):raise ValueError('Review flags must be true, false or null')
        if status!='unreviewed' and (not review['reviewer'].strip() or not review['notes'].strip()):raise ValueError('Reviewed records need reviewer and notes')
        if status=='approved' and (rid in blocked_ids or any(review[k] is not True for k in FLAGS)):
            raise ValueError('Approval requires all checks and an unblocked candidate')
        counts[status]+=1
    if seen!=set(expected):raise ValueError('Missing review records; export the complete queue')
    return {'counts':counts,'all_records_reviewed':counts['unreviewed']==0,
        'all_records_approved':counts['approved']==len(expected) and bool(expected),'approved_for_graph':False,
        'independent_gold':False,'limitations':'Development review attestation only; reviewer identity is not authenticated. Direct graph import remains disabled.'}
