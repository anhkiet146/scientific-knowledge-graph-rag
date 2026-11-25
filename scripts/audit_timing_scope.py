import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path
import shutil
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from workflow_io import atomic_json,file_hash


def seconds(row,key):
    value=row.get(key)
    if value is None:return None
    if type(value) not in (int,float) or not math.isfinite(value) or value<0:
        raise ValueError('Invalid measured duration: '+key)
    return value


def describe(values):
    if not values:return {'n':0,'mean':None,'median':None,'sample_sd':None,'p95_nearest_rank':None}
    ordered=sorted(values)
    return {'n':len(values),'mean':statistics.mean(values),'median':statistics.median(values),
        'sample_sd':statistics.stdev(values) if len(values)>1 else None,
        'p95_nearest_rank':ordered[math.ceil(.95*len(ordered))-1]}


def analyze(rows):
    seen=set();details=[];groups=defaultdict(list)
    for row in rows:
        key=row['question_id'],row['method']
        if key in seen:raise ValueError('Duplicate timing cell')
        seen.add(key)
        search=seconds(row,'search_seconds');embedding=seconds(row,'query_embedding_seconds')
        detail={'question_id':key[0],'method':key[1],'search_seconds':search,
            'query_embedding_seconds':embedding,
            'search_plus_embedding_seconds':search+embedding if search is not None and embedding is not None else None,
            'end_to_end_seconds':None,'context_packing_seconds':None,
            'scope':'Recorded partial stages only; missing is unknown, never zero'}
        details.append(detail);groups[key[1]].append(detail)
    summary={}
    for method,records in sorted(groups.items()):
        summary[method]={'records':len(records),'stages':{
            field:describe([r[field] for r in records if r[field] is not None])
            for field in ('search_seconds','query_embedding_seconds','search_plus_embedding_seconds')},
            'missing_partial_timings':sum(r['search_plus_embedding_seconds'] is None for r in records),
            'end_to_end_measured':False}
    return details,summary


def run(study,baseline,output):
    if output.exists():raise ValueError('Fresh output required')
    manifest=json.loads((study/'manifest.json').read_text(encoding='utf-8'))
    source=study/'contexts.jsonl'
    if file_hash(source)!=manifest['contexts_sha256']:raise ValueError('Contexts changed')
    if file_hash(baseline/'manifest.json')!=manifest['source_baseline_manifest_sha256']:
        raise ValueError('Baseline manifest changed')
    if file_hash(baseline/'contexts.jsonl')!=manifest['source_baseline_contexts_sha256']:
        raise ValueError('Baseline contexts changed')
    rows=[json.loads(s) for s in source.read_text(encoding='utf-8').splitlines()]
    if {(r['question_id'],r['method']) for r in rows}!={(q,m) for q in range(1,manifest['questions']+1) for m in manifest['methods']}:
        raise ValueError('Incomplete matched grid')
    details,summary=analyze(rows)
    setup=json.loads((baseline/'summary.json').read_text(encoding='utf-8'))
    setup={key:seconds(setup,key) for key in ('model_load_seconds','bm25_build_seconds')}
    output.mkdir(parents=True)
    with (output/'timing_by_question.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(details[0]));writer.writeheader();writer.writerows(details)
    atomic_json(output/'summary.json',{'methods':summary,'baseline_setup_seconds':setup,
        'quality_scores_computed':False,'actual_api_calls':0,'speedup_claim_supported':False,
        'limits':'One retrieval pass over 45 development questions, not five generation repeats. Search plus query embedding omits source selection, packing, generation, verification, network and throttle. Setup reported separately; cached corpus embedding cost is not zero. No comparable KG/end-to-end measurement exists in this input.'})
    atomic_json(output/'manifest.json',{'contexts_sha256':file_hash(source),'study_manifest_sha256':file_hash(study/'manifest.json'),
        'baseline_summary_sha256':file_hash(baseline/'summary.json'),'code_sha256':file_hash(Path(__file__))})
    shutil.copy2(Path(__file__),output/Path(__file__).name)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for flag in ('study','baseline','output'):parser.add_argument('--'+flag,type=Path,required=True)
    run(**vars(parser.parse_args()))
