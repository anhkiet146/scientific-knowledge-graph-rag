"""Question-level analysis of completed retrieval repeats, never QA quality."""
import argparse
import csv
import math
from pathlib import Path
import random
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/evaluation')]
from workflow_io import read_json,loads,atomic_json,file_hash
from revision_statistics import paired_inference,percentile

STAGES=('query_embedding_seconds','search_seconds','packing_seconds','retrieval_wall_seconds')


def analyze(rows,question_ids=tuple(range(1,46)),repeats=tuple(range(1,6)),draws=10000):
    if type(draws) is not int or draws<100:raise ValueError('At least100 resampling draws required')
    methods=('bm25','vector');grid={};hashes={}
    for row in rows:
        if type(row['question_id']) is not int or type(row['repeat']) is not int:raise ValueError('Integer question/repeat required')
        key=(row['method'],row['question_id'],row['repeat'])
        if key in grid:raise ValueError('Duplicate timing row')
        for stage in STAGES:
            value=row.get(stage)
            if type(value) not in (int,float) or not math.isfinite(value) or value<0:raise ValueError('Invalid stage duration')
        if not math.isclose(sum(row[s] for s in STAGES[:3]),row[STAGES[3]],rel_tol=1e-8,abs_tol=1e-8):
            raise ValueError('Stage durations do not equal retrieval wall interval')
        pair=key[:2]
        if pair in hashes and hashes[pair]!=row['context_sha256']:raise ValueError('Context changed across repeats')
        hashes[pair]=row['context_sha256'];grid[key]=row
    if set(grid)!={(m,q,r) for m in methods for q in question_ids for r in repeats}:
        raise ValueError('Complete paired question/repeat grid required')
    by_question=[];summary=[];means={}
    for method in methods:
        means[method]={}
        for stage in STAGES:
            qmeans=[statistics.mean(grid[method,q,r][stage] for r in repeats) for q in question_ids]
            means[method][stage]=qmeans
            rng=random.Random(20261117)
            samples=[statistics.mean(rng.choices(qmeans,k=len(qmeans))) for _ in range(draws)]
            summary.append({'method':method,'stage':stage,'unit':'seconds','n_questions':len(question_ids),
                'repeats_per_question':len(repeats),'mean':statistics.mean(qmeans),
                'bootstrap_95_ci':[percentile(samples,.025),percentile(samples,.975)],
                'sd_between_question_means':statistics.stdev(qmeans) if len(qmeans)>1 else None})
        for q in question_ids:
            values=[grid[method,q,r]['retrieval_wall_seconds'] for r in repeats]
            by_question.append({'method':method,'question_id':q,'repeats':len(values),
                'mean_seconds':statistics.mean(values),'within_question_sd_seconds':statistics.stdev(values) if len(values)>1 else None})
    differences=[v-b for v,b in zip(means['vector']['retrieval_wall_seconds'],means['bm25']['retrieval_wall_seconds'])]
    paired=paired_inference(differences,seed=20261117,draws=draws)
    paired.update(difference='vector minus bm25; positive means Vector retrieval is slower',unit='seconds',
                  holm_adjusted_p=paired['paired_sign_flip_p'],family_size=1)
    return {'analysis_scope':'Exploratory warm-retrieval timing only; not answer quality or end-to-end latency',
        'unit_of_inference':'question; repeats averaged within each question','records':len(rows),
        'summary':summary,'by_question':by_question,'paired_wall_time':paired,
        'statistical_plan':{'seed':20261117,'draws':draws,'bootstrap':'percentile question-mean bootstrap',
            'primary_comparisons':'one Vector-BM25 retrieval-wall comparison; Holm family size1',
            'stage_components':'descriptive CIs only; no extra stage-wise significance claims',
            'wilcoxon':'supplementary if available, not multiplicity-adjusted confirmatory evidence'},
        'api_calls':0,'quality_scores_computed':False,
        'limits':'Questions were used in development. One machine/session; query translation, index construction, generation, KG and LightRAG are excluded. Do not generalize to QA accuracy or total response speed.'}


def run(source,output):
    if output.exists():raise ValueError('Fresh analysis output required')
    manifest=read_json(source/'manifest.json')
    for name,field in [('timings.json','timings_sha256'),('contexts.jsonl','contexts_sha256'),('runtime.json','runtime_sha256')]:
        if file_hash(source/name)!=manifest[field]:raise ValueError('Timing/context/runtime artifact changed')
    rows=read_json(source/'timings.json');result=analyze(rows)
    contexts={(r['method'],r['question_id']):r for r in [loads(s) for s in (source/'contexts.jsonl').read_text(encoding='utf-8').split('\n') if s]}
    for row in rows:
        if contexts[row['method'],row['question_id']]['context_sha256']!=row['context_sha256']:
            raise ValueError('Timing belongs to another context')
    result['provenance']={'source_manifest_sha256':file_hash(source/'manifest.json'),
        'timings_sha256':file_hash(source/'timings.json'),'code_sha256':file_hash(Path(__file__)),
        'statistical_helper_sha256':file_hash(ROOT/'src/evaluation/revision_statistics.py')}
    output.mkdir(parents=True);atomic_json(output/'analysis.json',result)
    with (output/'question_means.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(result['by_question'][0]));writer.writeheader();writer.writerows(result['by_question'])
    table=[]
    for row in result['summary']:
        if row['stage']=='retrieval_wall_seconds':
            table.append({'method':row['method'],'mean_ms':row['mean']*1000,'ci_low_ms':row['bootstrap_95_ci'][0]*1000,
                          'ci_high_ms':row['bootstrap_95_ci'][1]*1000,'questions':45,'repeats':5})
    with (output/'retrieval_summary.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(table[0]));writer.writeheader();writer.writerows(table)
    print(table,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.source,a.output)
