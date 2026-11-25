import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import re
import shutil
import sys
import unicodedata

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'scripts')]
from workflow_io import atomic_json,read_json,file_hash
from prepare_review_dataset import verify


def filename_key(value):
    if not isinstance(value,str) or not value.strip():return None
    name=value.strip().replace('\\','/').rsplit('/',1)[-1]
    return unicodedata.normalize('NFC',Path(name).stem).casefold()


def title_key(value):
    return ' '.join(unicodedata.normalize('NFC',value).casefold().split()) if isinstance(value,str) else ''


def compare(frozen,live):
    by_name=defaultdict(list);by_title=defaultdict(list)
    for row in frozen:
        by_name[filename_key(row['filename'])].append(row['filename'])
        if title_key(row.get('title')):by_title[title_key(row['title'])].append(row['filename'])
    if any(len(v)>1 for v in by_name.values()):raise ValueError('Ambiguous frozen filename identity')
    if len({r['graph_id'] for r in live})!=len(live):raise ValueError('Duplicate graph element IDs')
    results=[];matched=Counter()
    for row in live:
        match=by_name.get(filename_key(row.get('filename')),[])
        suggestions=sorted(set(by_title.get(title_key(row.get('title') or row.get('name')),[])))
        if match:
            state='filename_match';matched[match[0]]+=1
        elif suggestions:state='title_candidate_needs_review'
        else:state='outside_frozen_inventory_unconfirmed'
        results.append({**row,'state':state,'frozen_filename':match[0] if match else None,'title_candidates':suggestions})
    summary={'frozen_papers':len(frozen),'live_paper_nodes':len(live),
        'states':dict(Counter(r['state'] for r in results)),
        'matched_unique_frozen_papers':len(matched),'missing_frozen_papers':sorted(set(r['filename'] for r in frozen)-set(matched)),
        'duplicate_live_nodes_for_frozen_filename':{k:v for k,v in matched.items() if v>1},
        'graph_writes_performed':False,'title_candidates_auto_accepted':False,
        'limits':'Filename identity only, not evidence that contents/extraction are unchanged. Unmatched nodes are not automatically proven new uploads.'}
    return results,summary


def run(dataset,inventory,output):
    if output.exists():raise ValueError('Fresh output required')
    verify(dataset)
    frozen=[{'filename':p.name,'title':read_json(p).get('title','')} for p in sorted((dataset/'corpus').glob('*.json'))]
    live=read_json(inventory)
    if not isinstance(live,list):raise ValueError('Expected Paper inventory array')
    rows,summary=compare(frozen,live)
    output.mkdir(parents=True)
    atomic_json(output/'paper_comparison.json',rows)
    atomic_json(output/'outside_or_pending.json',[r for r in rows if r['state']!='filename_match'])
    atomic_json(output/'summary.json',summary)
    atomic_json(output/'manifest.json',{'frozen_manifest_sha256':file_hash(dataset/'manifest.json'),'inventory_sha256':file_hash(inventory),'code_sha256':file_hash(Path(__file__))})
    shutil.copy2(Path(__file__),output/Path(__file__).name)
    print(json.dumps(summary,ensure_ascii=True,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for flag in ('dataset','inventory','output'):p.add_argument('--'+flag,type=Path,required=True)
    run(**vars(p.parse_args()))
