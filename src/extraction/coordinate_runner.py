"""Offline table pilot: source replay, field provenance and unlabelled review queue."""
import argparse
from pathlib import Path
import re
try:
    from .table_evidence import extract_table
    from .table_measurements import build_candidates
    from .workflow_io import read_json,canonical_hash,file_hash,atomic_json,RunLock
except ImportError:
    from table_evidence import extract_table
    from table_measurements import build_candidates
    from workflow_io import read_json,canonical_hash,file_hash,atomic_json,RunLock

VERSION='coordinate-table-pilot-v1'


def field_provenance(candidate,table):
    refs=candidate['source_cell_refs'];cells={c['id']:c for c in table['cells']}
    sources={'value':['value'],'uncertainty':['value'],'object':['object'],
        'endpoint':['unit','endpoint'] if 'unit' in refs else ['endpoint'],
        'unit':['unit'] if 'unit' in refs else ['value'],
        'condition':['condition_label','condition'] if 'condition' in refs else [],'source_report':['caption']}
    rules={'value':'parse_numeric_without_conversion','uncertainty':'parse_plus_minus_without_conversion',
        'unit':'reported_unit_without_conversion','object':'source_cell_text',
        'endpoint':'compose_header_and_endpoint_cells','condition':'compose_condition_header_and_value',
        'source_report':'explicit_table_layout'}
    result={}
    for field,roles in sources.items():
        keys=[refs[role] for role in roles if role in refs]
        rule=rules[field]
        if candidate['measurement'][field]=='':rule='not_reported_in_selected_cells'
        result[field]={'rule':rule,'cell_ids':keys,'cell_evidence_ids':[cells[k]['evidence_id'] for k in keys]}
    return result


def verified_bundle(pdf,spec,evidence):
    source=read_json(evidence);layout=read_json(spec)
    regenerated=extract_table(pdf,layout)
    if canonical_hash(source)!=canonical_hash(regenerated):raise ValueError('Evidence differs from PDF replay')
    candidates=build_candidates(source)
    for candidate in candidates['candidates']:
        candidate['field_provenance']=field_provenance(candidate,source) if candidate['measurement'] else {}
        candidate['review_id']=canonical_hash([source['source_sha256'],source['page'],source['spec_sha256'],candidate])
    return {'protocol_id':'coordinate-table-bundle-v1','table_evidence':source,'measurements':candidates,
        'source_replayed':True,'scope':'declared_table_only','approved_for_graph':False}


def immutable(path,value):
    if path.exists():
        if canonical_hash(read_json(path))!=canonical_hash(value):raise ValueError('Immutable pilot artifact changed: '+path.name)
    else:atomic_json(path,value)


def run(jobs_path,output):
    jobs_path=Path(jobs_path).resolve();output=Path(output).resolve();jobs=read_json(jobs_path)
    if not isinstance(jobs,list) or not jobs:raise ValueError('Nonempty job list required')
    prepared=[];seen=set()
    # Replay every input before emitting any review candidate.
    for job in jobs:
        if not isinstance(job,dict) or set(job)!={'id','pdf','spec','evidence'}:raise ValueError('Invalid table job')
        key=job['id']
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',key) or key in seen:
            raise ValueError('Safe unique job IDs required')
        seen.add(key);paths={}
        for name in ('pdf','spec','evidence'):
            if not isinstance(job[name],str):raise ValueError('Source path string required')
            p=Path(job[name]);p=(jobs_path.parent/p).resolve() if not p.is_absolute() else p.resolve()
            if not p.is_file() or p.is_relative_to(output):raise ValueError('Sources must be files outside output')
            paths[name]=p
        digests={name:file_hash(p) for name,p in paths.items()}
        bundle=verified_bundle(**paths)
        if any(file_hash(p)!=digests[name] for name,p in paths.items()):raise ValueError('Source changed during PDF replay')
        bundle['input_sha256']=digests
        prepared.append((key,paths,bundle))
    if jobs_path.is_relative_to(output):raise ValueError('Job list must be outside output')
    code_files=[Path(__file__).with_name(n) for n in ('coordinate_runner.py','table_evidence.py','table_measurements.py',
        'strict_validation.py','reextract_review.py','workflow_io.py','graph_policy.py')]
    manifest={'protocol_id':VERSION,'jobs_sha256':file_hash(jobs_path),'scope':'declared_tables_only',
        'code_sha256':{p.name:file_hash(p) for p in code_files},'job_definition_sha256':canonical_hash(jobs),
        'jobs':[{'id':k,'sources':{name:{'path':str(p),'sha256':bundle['input_sha256'][name]} for name,p in paths.items()}}
                for k,paths,bundle in prepared]}
    with RunLock(output):
        immutable(output/'manifest.json',manifest)
        policy=output/'policy_snapshot';policy.mkdir(exist_ok=True)
        for p in code_files:
            target=policy/p.name
            if target.exists() and file_hash(target)!=manifest['code_sha256'][p.name]:raise ValueError('Policy snapshot changed')
            if not target.exists():target.write_bytes(p.read_bytes())
        reviews=[];summary=[]
        for key,paths,bundle in prepared:
            snapshot=output/'sources'/key;snapshot.mkdir(parents=True,exist_ok=True)
            for name,p in paths.items():
                target=snapshot/(name+p.suffix)
                expected=bundle['input_sha256'][name]
                if file_hash(p)!=expected:raise ValueError('Input changed before snapshot')
                if target.exists() and file_hash(target)!=expected:raise ValueError('Source snapshot changed')
                if not target.exists():target.write_bytes(p.read_bytes())
                if file_hash(target)!=expected:raise ValueError('Source changed while snapshotting')
            immutable(output/'tables'/(key+'.json'),bundle)
            rows=bundle['measurements']['candidates']
            for row in rows:
                reviews.append({'review_id':row['review_id'],'job_id':key,'observation_id':row['observation_id'],
                    'candidate_sha256':canonical_hash(row),'source_pdf_sha256':bundle['table_evidence']['source_sha256'],
                    'review':{'status':'unreviewed','reviewer':'','notes':'','layout_correct':None,
                        'measurement_correct':None,'footnote_and_reporting_note_checked':None}})
            summary.append({'job_id':key,'candidates':len(rows),'blocked':sum(r['status']=='blocked' for r in rows)})
        # Human responses belong in a separate file; never replace filled reviews on resume.
        immutable(output/'review_template.json',{'purpose':'Development review, not independent gold',
            'manifest_sha256':canonical_hash(manifest),'records':reviews})
        result={'protocol_id':VERSION,'tables':summary,'actual_api_calls':0,'graph_writes':0,
            'approved_for_graph':0,'scope':'declared_tables_only','status':'blocked' if any(t['blocked'] for t in summary) else 'pending_human_review'}
        atomic_json(output/'summary.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=run(args.jobs,args.output)
    print('Offline coordinate pilot:',sum(t['candidates'] for t in result['tables']),'candidates;',result['status'],'; API calls: 0')


if __name__=='__main__':main()
