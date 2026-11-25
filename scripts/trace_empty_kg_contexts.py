"""Explain recorded empty contexts and controls; reject any selection drift."""
import argparse
import collections
import json
import os
import math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/evaluation'),str(ROOT/'src/extraction'),str(ROOT/'scripts')]
from prepare_review_dataset import verify
from snapshot_benchmark import SnapshotGraph
from hybrid_retrieval import rerank_candidates
from kg_ablation_preflight import VARIANTS
from context_budget import pack
from workflow_io import read_json,canonical_hash,file_hash,atomic_json


def run(dataset,preflight,cache,output):
    if output.exists():raise ValueError('Fresh trace output required')
    verify(dataset);manifest=read_json(preflight/'manifest.json')
    if file_hash(dataset/'manifest.json')!=manifest['dataset_manifest_sha256']:raise ValueError('Different frozen dataset')
    rows=[json.loads(s) for s in (preflight/'kg_contexts.jsonl').read_text(encoding='utf-8').split('\n') if s]
    empty=[r for r in rows if not r['context']];controls={}
    for row in rows:
        if row['context'] and row['method'] not in controls:controls[row['method']]=row
    cases=empty+list(controls.values())
    os.environ['TIKTOKEN_CACHE_DIR']=str(cache.resolve())
    import tiktoken
    enc=tiktoken.get_encoding(manifest['tokenizer']['encoding'])
    def encode(text):return enc.encode(text,disallowed_special=())
    graph=SnapshotGraph(dataset/'extracted');raw=SnapshotGraph(dataset/'extracted',normalize=False)
    output.mkdir(parents=True);summary=[];reason_counts=collections.Counter()
    def scientific_equal(a,b):
        if len(a)!=len(b):return False
        for first,second in zip(a,b):
            if {k:v for k,v in first.items() if k!='retrieval_score'}!={k:v for k,v in second.items() if k!='retrieval_score'}:return False
            x=first.get('retrieval_score');y=second.get('retrieval_score')
            if x!=y and (not isinstance(x,(int,float)) or not isinstance(y,(int,float)) or not math.isclose(x,y,rel_tol=1e-12,abs_tol=1e-12)):
                return False
        return True
    for row in cases:
        method=row['method'];options=VARIANTS[method];g=raw if options.get('raw') else graph
        candidates=g.retrieve(row['shared_query'],hops=options.get('hops',2));before=canonical_hash(candidates)
        kwargs={'max_context':8,'signal_multipliers':options.get('multipliers')}
        plain=rerank_candidates(row['shared_query'],row['query_plan'],candidates,**kwargs)
        trace={};traced=rerank_candidates(row['shared_query'],row['query_plan'],candidates,audit=trace,**kwargs)
        context,text,count=pack(traced,encode)
        if canonical_hash(candidates)!=before or plain!=traced:
            atomic_json(output/'replay_failure.json',{'question_id':row['question_id'],'method':method,
                'input_unchanged':canonical_hash(candidates)==before,'audit_selection_matches_plain':plain==traced,
                'context_matches_recorded':context==row['context'],'context_hash_matches':canonical_hash(text)==row['context_sha256'],
                'recorded_context':row['context'],'replayed_context':context,'audit_trace':trace})
            raise ValueError('Audit changed selection or candidate input')
        historical_equal=scientific_equal(context,row['context'])
        base=next((s['count'] for s in trace['stages'] if s['stage']=='base_direct_answers'),0)
        reason_counts.update(reason for candidate in trace.get('scored_candidates',[]) for reason in candidate['base_direct_rejection_reasons'])
        key=f"q{row['question_id']:02d}_{method}"
        atomic_json(output/(key+'.json'),{'question_id':row['question_id'],'method':method,'question':row['question'],
            'shared_query':row['shared_query'],'query_plan':row['query_plan'],'case_kind':'empty' if not row['context'] else 'nonempty_control',
            'candidate_inputs_sha256':before,'trace':trace,'audit_selection_identical_to_plain':True,
            'historical_scientific_context_matches':historical_equal,'historical_context_hash_matches':canonical_hash(text)==row['context_sha256'],
            'context_tokens':count,
            'independent_answerability':None,'quality_score':None})
        summary.append({'case':key,'kind':'empty' if not row['context'] else 'nonempty_control','termination':trace['termination'],
            'base_direct_count':base,'stages':trace['stages'],'audit_selection_identical_to_plain':True,
            'historical_scientific_context_matches':historical_equal,'historical_context_hash_matches':canonical_hash(text)==row['context_sha256']})
    verify(dataset)
    atomic_json(output/'summary.json',{'cases':summary,'empty_cases':len(empty),'nonempty_controls':len(controls),
        'all_audit_selections_identical_to_plain':True,
        'historical_scientific_matches':sum(c['historical_scientific_context_matches'] for c in summary),
        'historical_hash_matches':sum(c['historical_context_hash_matches'] for c in summary),
        'historical_comparison_rule':'Exact scientific/context fields, except retrieval_score alone permits 1e-12 floating-point drift. This is not used for measurement/gold scoring.',
        'base_rejection_reason_counts_nonexclusive':dict(reason_counts),
        'rerank_source_sha256':file_hash(ROOT/'src/retrieval/hybrid_retrieval.py'),
        'preflight_manifest_sha256':file_hash(preflight/'manifest.json'),'actual_api_calls':0,
        'quality_scores_computed':False,'limits':'Mechanical exclusion reasons only; no human truth labels or false-refusal conclusion. Description text is explicitly a preview.'})
    (output/'hybrid_retrieval_executed.py').write_bytes((ROOT/'src/retrieval/hybrid_retrieval.py').read_bytes())
    print('Traced',len(empty),'empty cases and',len(controls),'controls; audit equals plain selection',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('dataset','preflight','cache','output'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args();run(**vars(args))
