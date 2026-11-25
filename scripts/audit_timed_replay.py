import argparse
import json
import math
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from workflow_io import atomic_json,file_hash
from audit_timing_scope import describe


def validate_timing(row):
    timing=row['timing']
    kg='track' in row
    fields=('source_selection_seconds','search_expansion_candidates_seconds','planning_ranking_seconds','packing_seconds') if kg else (
        'source_selection_seconds','search_seconds','query_embedding_seconds','packing_seconds')
    total='retrieval_wall_seconds' if kg else 'retrieval_stage_sum_seconds'
    for key in (*fields,total):
        value=timing[key]
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:raise ValueError('Invalid timing: '+key)
    if not math.isclose(sum(timing[k] for k in fields),timing[total],rel_tol=1e-9,abs_tol=1e-9):
        raise ValueError('Stage accounting mismatch')
    return fields,total


def compare(old,new):
    key=lambda r:(r['question_id'],r.get('track',r.get('method')))
    before={key(r):r for r in old};after={key(r):r for r in new}
    if len(before)!=len(old) or len(after)!=len(new) or set(before)!=set(after):raise ValueError('Grid changed')
    for cell,row in after.items():
        for field in ('question','shared_query','context_json','context_sha256','context_tokens','paper_scope'):
            if before[cell][field]!=row[field]:raise ValueError('Frozen retrieval changed: '+field)
        validate_timing(row)
    return len(after)


def run(previous,current,output):
    if output.exists():raise ValueError('Fresh output required')
    load=lambda p:[json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s]
    groups={};hashes={};count=0
    for folder,filename,oldfolder in [('kg','paired_contexts.jsonl','kg_ablations'),('baselines','contexts.jsonl','baselines')]:
        oldpath=previous/oldfolder/filename;newpath=current/folder/filename
        old,new=load(oldpath),load(newpath);count+=compare(old,new)
        hashes[str(oldpath.resolve())]=file_hash(oldpath);hashes[str(newpath.resolve())]=file_hash(newpath)
        for row in new:
            method=row.get('track',row.get('method'));groups.setdefault(method,[]).append(row)
    summary={}
    for method,rows in groups.items():
        fields,total=validate_timing(rows[0])
        summary[method]={'questions':len(rows),'timing_scope':rows[0]['timing']['scope'],
            'total_field':total,'stages':{field:describe([r['timing'][field] for r in rows]) for field in (*fields,total)}}
    output.mkdir(parents=True)
    atomic_json(output/'summary.json',{'records_replayed':count,'contexts_identical_to_previous':True,
        'stage_accounting_valid':True,'methods':summary,'actual_api_calls':0,'end_to_end_qa_measured':False,
        'execution':'KG process completed before baseline process was launched; one replay per question, no process overlap between these two measured runs.',
        'limits':'Development retrieval only. Different evidence representations, fixed order, uncontrolled OS load/cache; not five repeats, not Neo4j latency, no QA superiority or end-to-end speedup claim.'})
    code=[Path(__file__),Path(__file__).with_name('compare_normalization_retrieval.py'),Path(__file__).with_name('matched_scoped_baselines.py'),Path(__file__).with_name('audit_timing_scope.py')]
    atomic_json(output/'manifest.json',{'data_sha256':hashes,'code_sha256':{p.name:file_hash(p) for p in code}})
    for path in code:shutil.copy2(path,output/path.name)
    print(json.dumps({'records':count,'contexts_unchanged':True,'methods':{m:round(r['stages'][r['total_field']]['mean']*1000,3) for m,r in summary.items()}},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for flag in ('previous','current','output'):parser.add_argument('--'+flag,type=Path,required=True)
    run(**vars(parser.parse_args()))
