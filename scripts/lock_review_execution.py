"""Audit all frozen contexts and lock a no-API repeated run grid, without gold."""
import argparse
import collections
import json
from pathlib import Path
import random
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/evaluation'),str(ROOT/'src/retrieval')]
from workflow_io import atomic_json,file_hash,canonical_hash
from controlled_generation_pilot import BASE_METHODS,load_contexts
from claim_verification import filter_claims_v2


def run(context_file,output,old_pilot):
    if output.exists():raise ValueError('Choose fresh output; never overwrite a locked run')
    rows=[json.loads(line) for line in context_file.read_text(encoding='utf-8').splitlines() if line.strip()]
    expected={(q,m) for q in range(1,46) for m in (*BASE_METHODS,'kg_verified')}
    keys=[(r['question_id'],r['method']) for r in rows]
    if len(keys)!=len(set(keys)) or set(keys)!=expected:raise ValueError('Incomplete or duplicated 45 x 8 grid')
    for q in range(1,46):load_contexts(context_file,q)
    output.mkdir(parents=True)
    # Existing verdicts lack atomicity; do not manufacture atomic labels offline.
    replay=[]
    for file in sorted((old_pilot/'records').glob('*kg_verified.json')):
        record=json.loads(file.read_text(encoding='utf-8'))
        contexts=load_contexts(context_file,record['question_id'])['kg']['context']
        answer,audit=filter_claims_v2(record['draft_answer'],contexts,{'claims':record['claim_audit']})
        replay.append({'record':file.name,'original_record_sha256':file_hash(file),'v2_answer':answer,'audit':audit,
                       'limits':'Old model verdict, not v2 prompt output; missing atomicity is intentionally rejected, no quality inference.'})
    atomic_json(output/'legacy_verdict_replay.json',replay)
    grid=[]
    for repeat in range(1,6):
        questions=list(range(1,46));random.Random(20261115+repeat).shuffle(questions)
        for q in questions:
            methods=list(BASE_METHODS);random.Random(20261115+100*repeat+q).shuffle(methods)
            for method in methods+['kg_verified']:
                grid.append({'question_id':q,'repeat':repeat,'method':method,'state':'not_run',
                             'draft_dependency':f'{q}:{repeat}:kg' if method=='kg_verified' else None,
                             'quality_score':None})
    atomic_json(output/'run_grid.json',grid)
    counts=collections.Counter(r['method'] for r in rows if not r['context'])
    audit={'records':len(rows),'questions':45,'methods':8,'paired_contexts_identical':True,
           'empty_contexts_by_method':dict(counts),'actual_api_calls':0,'quality_scores_computed':False}
    atomic_json(output/'context_audit.json',audit)
    files=[context_file,ROOT/'src/retrieval/claim_verification.py',ROOT/'src/evaluation/snapshot_benchmark.py',
           ROOT/'src/evaluation/controlled_generation_pilot.py',Path(__file__)]
    lock={'protocol_id':'review-locked-offline-v2','state':'offline_contract_locked_live_execution_pending',
          'questions':45,'repeats':5,'inference_unit':'question; average repeats within question',
          'methods':list(BASE_METHODS)+['kg_verified'],'generator':'gemini-2.5-flash','temperature':0,
          'thinking_budget':0,'answer_output_tokens':1024,'verification_output_tokens':4096,
          'context_budget':{'limit':2000,'encoding':'o200k_base','scope':'common proxy, not provider tokenizer'},
          'queries':'Frozen cached shared queries; no per-method translation calls',
          'verifier':'v2 opt-in; identical KG draft and context; atomicity and entailment remain model judgments',
          'controlled_requests_without_failures':1800,'retry_policy':'No automatic paid retries',
          'sota_track':{'implementation':'LightRAG 1.5.7','status':'full-corpus indexing pending',
                        'embedding':'all-MiniLM-L6-v2 same cached weights as vector baseline',
                        'minimum_answer_calls':225,'indexing_keyword_calls':'unknown, measure and budget separately',
                        'comparison':'separate native whole-system track; disclose native prompts and query stages'},
          'live_api_calls_authorized_by_this_lock':0,'independent_labels_required_for_quality_reporting':True,
          'timing':'Report indexing, retrieval, generation HTTP, verification HTTP, throttle and total separately',
          'corpus_status':'historical extraction; cannot claim strict-v3.1 full reextraction',
          'files':{str(p.resolve()):file_hash(p) for p in files},'grid_sha256':file_hash(output/'run_grid.json'),
          'limits':'Not a full-study runner. Paid execution and SOTA data preparation remain pending. No quality claims from structural checks.'}
    atomic_json(output/'protocol_lock.json',lock)
    print(json.dumps(audit,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('contexts','output','old-pilot'):p.add_argument('--'+flag,type=Path,required=True)
    a=p.parse_args();run(a.contexts,a.output,a.old_pilot)
