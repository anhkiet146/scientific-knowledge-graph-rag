import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/retrieval'),str(ROOT/'src/extraction')]
import claim_verification as old
import claim_verification_experimental as new
from workflow_io import atomic_json, file_hash


def run(source, output):
    if output.exists():raise ValueError('Fresh output required')
    manifest=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    fixture=source/'synthetic_cases.jsonl'
    if file_hash(fixture)!=manifest['cases_sha256']:raise ValueError('Fixture hash changed')
    if file_hash(Path(old.__file__))!=manifest['code_sha256']['claim_verification.py']:
        raise ValueError('Frozen verifier changed')
    rows=[json.loads(s) for s in fixture.read_text(encoding='utf-8').splitlines()]
    if len({r['case_id'] for r in rows})!=len(rows):raise ValueError('Duplicate case IDs')
    results=[]
    for row in rows:
        answer,audit=new.filter_claims_experimental(row['draft'],row['contexts'],row['verdict'])
        results.append({'case_id':row['case_id'],'group':row['group'],
            'v2_accepted':row['actual_structural_acceptance'],
            'experimental_accepted':any(r['accepted'] for r in audit),
            'experimental_answer':answer,'experimental_audit':audit})
    summary={'synthetic_cases':len(rows),'groups':dict(Counter(r['group'] for r in rows)),
        'newly_blocked_cases':[r['case_id'] for r in results if r['v2_accepted'] and not r['experimental_accepted']],
        'remaining_known_gap_cases':[r['case_id'] for r in results if r['group']=='known_semantic_gap' and r['experimental_accepted']],
        'supported_controls_retained':sum(r['experimental_accepted'] for r in results if r['group']=='supported_control'),
        'structural_guard_cases_still_rejected':sum(not r['experimental_accepted'] for r in results if r['group']=='structural_guard'),
        'actual_api_calls':0,'active_runner_changed':False,'qa_quality_measured':False,
        'limits':'Developer fixtures only; no model verdict sampling or independent gold. Cannot estimate real precision, hallucination reduction or false refusal rate. Strict numeric forms can cause false refusals.'}
    output.mkdir(parents=True)
    with (output/'comparison.jsonl').open('w',encoding='utf-8') as f:
        for row in results:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    atomic_json(output/'summary.json',summary)
    code=[Path(__file__),Path(old.__file__),Path(new.__file__)]
    atomic_json(output/'manifest.json',{'fixture_sha256':file_hash(fixture),'source_manifest_sha256':file_hash(source/'manifest.json'),
        'code_sha256':{p.name:file_hash(p) for p in code}})
    for path in code:shutil.copy2(path,output/path.name)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    run(**vars(p.parse_args()))
