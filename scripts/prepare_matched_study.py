import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/evaluation')]
from workflow_io import atomic_json,canonical_hash,file_hash
from controlled_generation_pilot import BASE_METHODS


def lines(path):return [json.loads(s) for s in path.read_text(encoding='utf-8').split('\n') if s]


def assemble(baselines,kg,output):
    if output.exists():raise ValueError('Fresh output required')
    rows=lines(baselines/'contexts.jsonl')
    renames={'raw':'kg_raw','pdf_alias_source_checked':'kg','no_expansion':'kg_no_expansion','no_semantic':'kg_no_semantic','no_relation':'kg_no_relation'}
    for row in lines(kg/'paired_contexts.jsonl'):
        if row['track'] not in renames:continue
        result=copy.deepcopy(row);result['method']=renames[row['track']];rows.append(result)
        if result['method']=='kg':
            paired=copy.deepcopy(result);paired['method']='kg_verified';paired['pairing']='Reuse exact kg draft, not a separate generated answer';rows.append(paired)
    grid={}
    for row in rows:
        key=row['question_id'],row['method']
        if key in grid:raise ValueError('Duplicate record')
        grid[key]=row
        text=json.dumps(row['context'],ensure_ascii=False,sort_keys=True,separators=(',',':'))
        if text!=row['context_json'] or canonical_hash(text)!=row['context_sha256'] or not 0<=row['context_tokens']<=2000:raise ValueError('Context contract mismatch')
        if row['method']=='kg_no_expansion' and any('relation' in c for c in row['context']):raise ValueError('Neighborhood evidence leaked into no-expansion context')
    methods=(*BASE_METHODS,'kg_verified')
    if set(grid)!={(q,m) for q in range(1,46) for m in methods}:raise ValueError('Incomplete matched grid')
    for q in range(1,46):
        records=[grid[q,m] for m in methods]
        if len({r['question'] for r in records})!=1 or len({r['shared_query'] for r in records})!=1:raise ValueError('Different query/question')
        if len({canonical_hash(r['paper_scope']) for r in records})!=1:raise ValueError('Different source selection policy result')
        if grid[q,'kg']['context_json']!=grid[q,'kg_verified']['context_json']:raise ValueError('Verifier context differs')
    output.mkdir(parents=True)
    with (output/'contexts.jsonl').open('w',encoding='utf-8') as f:
        for key in sorted(grid):f.write(json.dumps(grid[key],ensure_ascii=False)+'\n')
    atomic_json(output/'manifest.json',{'protocol_id':'matched-generation-development-v2','source_baseline_manifest_sha256':file_hash(baselines/'manifest.json'),
        'source_kg_manifest_sha256':file_hash(kg/'manifest.json'),'source_baseline_contexts_sha256':file_hash(baselines/'contexts.jsonl'),
        'source_kg_contexts_sha256':file_hash(kg/'paired_contexts.jsonl'),'contexts_sha256':file_hash(output/'contexts.jsonl'),
        'methods':list(methods),'questions':45,'planned_repeats':5,'planned_controlled_calls':1800,'actual_api_calls':0,
        'preprocessing':'Identical frozen query, title-based source scope and 2000 proxy-token cap; same generator prompt/settings in QA runner.',
        'limits':'Different evidence representations and index inputs are disclosed: passage BM25/Vector vs entity/edge KG. KG raw vs full includes alias endpoint repairs. Known development questions; no unseen-test claim. LightRAG native track not included.',
        'code_sha256':file_hash(Path(__file__))})
    atomic_json(output/'audit.json',{'status':'passed','records':360,'questions':45,'methods':8,'question_query_scope_identical':True,
        'verification_context_identical':True,'no_expansion_relation_evidence_absent':True,'max_tokens':max(r['context_tokens'] for r in rows),
        'empty_by_method':{m:sum(not r['context'] for r in rows if r['method']==m) for m in methods},'quality_scores_computed':False})
    print('Prepared matched grid: 360 records, 8 methods, 45 questions; no generation calls')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for flag in ('baselines','kg','output'):p.add_argument('--'+flag,type=Path,required=True)
    assemble(**vars(p.parse_args()))
