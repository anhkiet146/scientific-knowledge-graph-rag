"""Audit the small pilot and prepare unlabelled judgments; no QA quality score."""
import argparse
import collections
import json
from pathlib import Path
import random
import statistics
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/evaluation'),str(ROOT/'src/retrieval')]
from workflow_io import read_json,atomic_json,file_hash,canonical_hash
from controlled_generation_pilot import BASE_METHODS,parse_verdict
from snapshot_benchmark import generation_prompt
from claim_verification import filter_claims


def analyze(prior,current,output):
    if output.exists():raise ValueError('Fresh analysis directory required')
    contexts=read_json(current/'selected_contexts.json');manifest=read_json(current/'manifest.json')
    prior_manifest=read_json(prior/'manifest.json')
    if manifest['prior_manifest_sha256']!=file_hash(prior/'manifest.json'):raise ValueError('Different prior run')
    if manifest['contexts_sha256']!=prior_manifest['contexts_sha256']:raise ValueError('Context changed')
    responses=[];usage=collections.Counter()
    for folder in (prior,current):
        journal=sorted((folder/'provider_journal').glob('*/response.json'))
        if len(journal)!=8:raise ValueError('Expected exactly eight received responses per phase')
        for path in journal:
            raw=read_json(path);request=read_json(path.parent/'request.json');outcome=read_json(path.parent/'outcome.json')
            if request['body_sha256']!=canonical_hash(request['body']):raise ValueError('Request changed')
            if raw['candidates'][0]['finishReason']!='STOP' or outcome['state']!='received':raise ValueError('Incomplete response')
            for k,v in raw.get('usageMetadata',{}).items():
                if type(v) is int:usage[k]+=v
            responses.append({'phase':folder.name,'slot':path.parent.name,'response_sha256':file_hash(path),'request_seconds':outcome['request_seconds'],
                'throttle_wait_seconds':outcome.get('throttle_wait_seconds',0),'returned_model':raw.get('modelVersion')})
    rows=[];times=collections.defaultdict(list);verification=[];normalization=[]
    for repeat,folder in ((1,prior),(2,current)):
        for method in BASE_METHODS:
            row=read_json(current/'records'/f'r{repeat}_{method}.json')
            if row['generation_status']!='success' or row['context_sha256']!=contexts[method]['context_sha256']:raise ValueError('Incomplete/mismatched generation')
            request=read_json(folder/'provider_journal'/f"{row['provider_call']:04d}"/'request.json')
            expected=generation_prompt(row['question'],contexts[method]['context'])
            if request['body']['contents'][-1]['parts'][0]['text']!=expected:raise ValueError('Generation did not use frozen common prompt/context')
            raw_generation=read_json(folder/'provider_journal'/f"{row['provider_call']:04d}"/'response.json')
            received=''.join(p.get('text','') for p in raw_generation['candidates'][0]['content']['parts'] if not p.get('thought'))
            if received!=row['draft_answer'] or received!=row['generated_answer'] or row['method']!=method or row['repeat']!=repeat:
                raise ValueError('Stored answer/identity differs from received provider response')
            outcome=read_json(folder/'provider_journal'/f"{row['provider_call']:04d}"/'outcome.json')
            times[method].append(outcome['request_seconds']);rows.append(row)
        kg=read_json(current/'records'/f'r{repeat}_kg.json');raw_answer=read_json(current/'records'/f'r{repeat}_kg_raw.json')
        verified=read_json(current/'records'/f'r{repeat}_kg_verified.json')
        if verified['draft_answer']!=kg['draft_answer']:raise ValueError('Verification used another draft')
        raw=read_json(folder/'provider_journal/0008/response.json');text=''.join(p.get('text','') for p in raw['candidates'][0]['content']['parts'] if not p.get('thought'))
        verdict,wrapped=parse_verdict(text);answer,audit=filter_claims(kg['draft_answer'],contexts['kg']['context'],verdict)
        if answer!=verified['generated_answer'] or audit!=verified['claim_audit']:raise ValueError('Verification replay differs')
        outcome=read_json(folder/'provider_journal/0008/outcome.json')
        times['kg_verified'].append(times['kg'][-1]+outcome['request_seconds'])
        verification.append({'repeat':repeat,'verifier_records':len(audit),'accepted_records':sum(c['accepted'] for c in audit),
            'distinct_accepted_texts':len({c['text'] for c in audit if c['accepted']}),'output_changed':answer!=kg['draft_answer'],
            'transport_wrapper_removed':wrapped,'independent_faithfulness':None,'independent_false_refusal':None})
        normalization.append({'repeat':repeat,'raw_vs_normalized_identical_text':raw_answer['generated_answer']==kg['generated_answer'],
            'independent_correctness_raw':None,'independent_correctness_normalized':None})
        rows.append(verified)
    output.mkdir(parents=True)
    atomic_json(output/'audit.json',{'status':'passed','responses':len(responses),'logical_answer_records':len(rows),
        'same_draft_pairing_verified':True,'generation_prompt_context_replay_verified':True,'usage':dict(usage),
        'provider_responses':responses,'quality_scores_computed':False,'graph_writes':0})
    atomic_json(output/'descriptive_diagnostics.json',{'question_count':1,'repeats':2,
        'provider_timing':{method:{'n':len(v),'mean_seconds':statistics.mean(v),'sample_sd_seconds':statistics.stdev(v),
            'values':v} for method,v in times.items()},'verification':verification,'normalization':normalization,
        'timing_scope':'API-adapter HTTP request plus parsing/journaling overhead, excluding intentional throttle and frozen retrieval. KG verified allocates shared KG draft plus verifier request; not independent end-to-end latency.',
        'no_significance_tests':'One known question with no independent scores cannot support QA significance or generalization.'})
    shuffled=rows.copy();random.Random(20261115).shuffle(shuffled);blind=[];mapping=[]
    for index,row in enumerate(shuffled,1):
        identifier=f'pilot-{index:03d}'
        blind.append({'item_id':identifier,'question':row['question'],'answer':row['generated_answer'],
            'evidence_context':contexts[row['method']]['context'],'reviewer':None,'correctness_raw_0_1_2':None,
            'source_answerability':None,'unsupported_claims':None,'false_refusal':None,'source_evidence':[],'notes':None})
        mapping.append({'item_id':identifier,'method':row['method'],'repeat':row['repeat'],'record_sha256':canonical_hash(row)})
    for role in ('A','B'):
        atomic_json(output/f'judge_{role}_blank.json',{'purpose':'Independent pilot-output review, not adjudicated gold',
            'instructions':'Do not consult the method key or other reviewer. Check original sources; retrieval format may reveal the system. Existing reference answers have not been inserted.',
            'tasks':blind})
    atomic_json(output/'method_key_do_not_send_to_judges.json',mapping)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('prior','current','output'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args();analyze(**vars(args))
