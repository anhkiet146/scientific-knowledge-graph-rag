import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/retrieval'),str(ROOT/'src/evaluation')]
from workflow_io import atomic_json,canonical_hash,file_hash,read_json
from hybrid_retrieval import rerank_candidates
from context_budget import evidence_units,pack_v2

WEIGHTS={'semantic':.32,'entity':.14,'answer_type':.16,'relation':.11,'path':.09,'source':.05,'evidence':.08,'retrieval':.04,'degree':.01}


def validate_candidates(cases):
    for case in cases:
        for candidate in case['candidates']:
            for connection in candidate.get('connections',[]):
                if not isinstance(connection.get('relation'),str) or not connection['relation'].strip():raise ValueError('Untyped graph connection: relation sensitivity invalid')


def variants():
    yield 'baseline',{}
    for name in WEIGHTS:
        for factor in (0,.5,2):yield f'{name}_x{factor:g}',{name:factor}


def run(snapshot,cache,output):
    if output.exists():raise ValueError('Fresh output required')
    import tiktoken.load
    def offline(*args,**kwargs):raise RuntimeError('Cached tokenizer required')
    tiktoken.load.read_file=offline;os.environ['TIKTOKEN_CACHE_DIR']=str(cache.resolve())
    import tiktoken
    enc=tiktoken.get_encoding('o200k_base');encode=lambda text:enc.encode(text,disallowed_special=())
    files=sorted(snapshot.glob('q*.json'));cases=[read_json(p) for p in files]
    if len(cases)!=45 or {c['question_id'] for c in cases}!=set(range(1,46)):raise ValueError('45 fixed candidate sets required')
    validate_candidates(cases)
    output.mkdir(parents=True);rows=[];totals=defaultdict(lambda:{'changed_ranked_order':0,'changed_contexts':0,'empty_contexts':0,'max_context_tokens':0})
    baseline={}
    with (output/'measurements.jsonl').open('w',encoding='utf-8') as stream:
        for case in cases:
            for name,multipliers in variants():
                ranked=rerank_candidates(case['shared_query'],case['plan'],case['candidates'],max_context=8,signal_multipliers=multipliers)
                context,text,count,_=pack_v2(evidence_units(ranked),encode)
                order=[(r['entity_type'],r['entity_name'],r['source_papers']) for r in ranked]
                value={'order':order,'context_sha256':canonical_hash(text)}
                if name=='baseline':baseline[case['question_id']]=value
                reference=baseline[case['question_id']]
                changed_order=order!=reference['order'];changed_context=value['context_sha256']!=reference['context_sha256']
                row={'question_id':case['question_id'],'variant':name,'multipliers':multipliers,
                     'ranked_order':order,'context':context,'context_sha256':value['context_sha256'],'context_tokens':count,
                     'changed_ranked_order':changed_order,'changed_context':changed_context,'empty_context':not context,'quality_score':None}
                stream.write(json.dumps(row,ensure_ascii=False)+'\n')
                summary=totals[name];summary['changed_ranked_order']+=changed_order;summary['changed_contexts']+=changed_context
                summary['empty_contexts']+=not context;summary['max_context_tokens']=max(summary['max_context_tokens'],count)
            print('question',case['question_id'],'complete',flush=True)
    atomic_json(output/'summary.json',{'questions':45,'variants':28,'measurements':1260,'base_weights':WEIGHTS,
        'results':dict(totals),'actual_api_calls':0,'quality_scores_computed':False,'weights_selected_from_results':False,
        'scope':'Sensitivity of candidate ordering and packed context only. Normalize remaining effective weights by their sum; task-specific score bonuses and filters retained.',
        'limits':'Known development questions, not unseen evaluation. Context changes/unchanged contexts are not quality gains or significance. Base weights retained, not optimized on this set.'})
    atomic_json(output/'manifest.json',{'code_sha256':file_hash(Path(__file__)),'candidate_files_sha256':{p.name:file_hash(p) for p in files},
        'dependencies':{p.name:file_hash(p) for p in [ROOT/'src/retrieval/hybrid_retrieval.py',ROOT/'src/evaluation/context_budget.py']},
        'policy':'One coefficient at a time x0/x0.5/x2; same frozen candidates/query/plan/context budget. No generator calls or labels.'})
    print('Sensitivity complete: 1260 measurements')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for flag in ('snapshot','cache','output'):p.add_argument('--'+flag,type=Path,required=True)
    run(**vars(p.parse_args()))
