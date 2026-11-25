import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from workflow_io import atomic_json,file_hash


def risk_flags(a,b):
    flags=[];ta=set(re.findall(r'\w+',a.casefold()));tb=set(re.findall(r'\w+',b.casefold()))
    if re.findall(r'\d+(?:\.\d+)?',a)!=re.findall(r'\d+(?:\.\d+)?',b):flags.append('numeric_or_version_difference')
    negation={'non','not','without','no'}
    variants={'small','large','base','tiny','mini','xl','xxl','ground','unground','treated','untreated','modified','unmodified','positive','negative','uniform','nonuniform'}
    if ta&negation!=tb&negation:flags.append('negation_difference')
    if ta&variants!=tb&variants:flags.append('variant_or_condition_difference')
    ca=re.search(r'\bO\s*\(([^)]+)\)',a);cb=re.search(r'\bO\s*\(([^)]+)\)',b)
    if ca and cb and re.sub(r'\s','',ca[1])!=re.sub(r'\s','',cb[1]):flags.append('complexity_expression_difference')
    return flags


def run(candidates,output):
    if output.exists():raise ValueError('Fresh output required')
    rows=[json.loads(s) for s in candidates.read_text(encoding='utf-8').split('\n') if s]
    if len({r['candidate_id'] for r in rows})!=len(rows):raise ValueError('Duplicate candidate IDs')
    for row in rows:
        row['risk_flags']=risk_flags(row['name_a'],row['name_b'])
        row['review_priority']='qualifier_check_first' if row['risk_flags'] else 'same_paper_source_check' if row['shared_papers'] else 'cross_paper_identity_check'
    output.mkdir(parents=True)
    with (output/'candidates_with_risks.jsonl').open('w',encoding='utf-8') as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    with (output/'review_queue.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['candidate_id','type','name_a','name_b','cosine','shared_papers','risk_flags','review_priority','decision','pdf_source','page','quote','notes'])
        for row in rows:w.writerow([row['candidate_id'],row['type'],row['name_a'],row['name_b'],row['cosine'],';'.join(row['shared_papers']),';'.join(row['risk_flags']),row['review_priority'],'pending_source_review','','','',''])
    summary={'candidate_pairs':len(rows),'pairs_with_risk_flags':sum(bool(r['risk_flags']) for r in rows),
        'flags':dict(Counter(flag for r in rows for flag in r['risk_flags'])),'priorities':dict(Counter(r['review_priority'] for r in rows)),
        'graph_merges_applied':0,'quality_scores_computed':False,'actual_api_calls':0,
        'limits':'Warnings are review cues, not different-entity gold. Numeric wording such as five/5 can cause warnings despite possible identity; never auto-merge unflagged pairs.'}
    atomic_json(output/'summary.json',summary)
    atomic_json(output/'manifest.json',{'input_sha256':file_hash(candidates),'code_sha256':file_hash(Path(__file__))})
    print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--candidates',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    run(**vars(p.parse_args()))
