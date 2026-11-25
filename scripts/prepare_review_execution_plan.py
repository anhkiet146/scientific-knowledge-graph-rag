"""Freeze a blocked experiment design and empty run grid. Never sends API requests."""
import argparse
import itertools
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'scripts')]
from workflow_io import read_json,atomic_json,file_hash,canonical_hash
from prepare_review_dataset import verify

METHODS=['bm25','vector','kg','kg_no_expansion','kg_raw','kg_no_semantic','kg_no_relation','kg_verified']


def budget(questions,repeats,methods,*,released_methods=1):
    if any(type(v) is not int or v<1 for v in (questions,repeats,methods)) or type(released_methods) is not int or released_methods<0:
        raise ValueError('Positive design counts required')
    pairs=questions*repeats
    parts={'controlled_answer_calls':pairs*methods,'shared_query_analysis_calls':pairs,
        'claim_verification_calls':pairs,'released_answer_calls':pairs*released_methods,
        'released_native_keyword_calls':pairs*released_methods}
    return {'online_scenario_calls':sum(parts.values()),'components':parts,
        'assumptions':'One call per declared stage, no cache/retry; native LightRAG is a separate whole-system track. Extra calls may be required.',
        'released_indexing_calls':None,'extraction_rerun_calls':None,'judge_api_calls':0,
        'full_total_calls':None,'cost_money':None,
        'limits':'Scenario, not measured quota or a safe upper bound. Indexing/summary/retry requirements are unknown; no paid batch authorized by this plan.'}


def annotation_readiness(folder):
    folder=Path(folder);manifest=read_json(folder/'manifest.json')
    for record in manifest['files']:
        p=(folder/record['path']).resolve()
        if not p.is_relative_to(folder.resolve()) or file_hash(p)!=record['sha256']:raise ValueError('Annotation template/source changed')
    result={}
    for label in ('A','B'):
        tasks=[json.loads(line) for line in (folder/f'annotator_{label}_extraction.jsonl').read_text(encoding='utf-8').split('\n') if line]
        qa=read_json(folder/f'annotator_{label}_qa.json')['tasks']
        if len(tasks)!=40 or len(qa)!=45:raise ValueError('Incorrect independent task counts')
        if any(t['protocol_id']!='strict-extraction-v3.1' for t in tasks):raise ValueError('Annotation protocol mismatch')
        result[label]={'extraction_tasks':len(tasks),'qa_tasks':len(qa),
            'pending_extraction':sum(t['annotation_status']=='pending' for t in tasks),
            'pending_qa':sum(t['annotation_status']=='pending' for t in qa)}
    # A prepared blank bundle never establishes gold, even if edited status text looks complete.
    return {'task_counts':result,'gold_ready':False,'adjudication_ready':False,
        'reason':'Independent completed submissions, source validation, agreement and adjudicated gold artifacts required separately.'}


def prepare(dataset,annotation,vector_run,released_root,output):
    output=Path(output).resolve()
    if output.exists():raise ValueError('Fresh plan output required')
    frozen=verify(dataset);labels=annotation_readiness(annotation)
    if frozen['n_questions']!=45:raise ValueError('Expected 45 QA questions')
    vector=read_json(vector_run/'manifest.json');vector_summary=read_json(vector_run/'summary.json')
    released=read_json(released_root/'artifact_audit.json')
    if vector['dataset_manifest_sha256']!=file_hash(dataset/'manifest.json') or vector_summary['n_records']!=90:
        raise ValueError('Vector evidence does not match frozen QA corpus')
    if released['status']!='passed':raise ValueError('Released smoke has not passed')
    plan={'protocol_id':'review-comparison-design-v1','status':'blocked_not_execution_approved',
        'qa_corpus_manifest_sha256':file_hash(dataset/'manifest.json'),'annotation_template_manifest_sha256':file_hash(annotation/'manifest.json'),
        'controlled_track':{'methods':METHODS,'question_ids':list(range(1,46)),'repeats':[1,2,3,4,5],
            'reference':'kg','metrics':['correctness'],'generator':'gemini-2.5-flash','temperature':0,'thinking_budget':0,
            'max_output_tokens':1024,'context_budget':{'kind':'common tokenizer tokens','max':2000,'tokenizer_artifact':'UNRESOLVED_NOT_LOCKED'},
            'warning':'Existing 12000-character retrieval preflight is not this token-budget protocol; all adapters must be validated before activation.'},
        'whole_system_track':{'method':'released_lightrag_1_5_7','question_ids':list(range(1,46)),'repeats':[1,2,3,4,5],
            'reference_comparison':'Separate whole-system table; do not pool into controlled retrieval-only attribution',
            'full_corpus_index_ready':False,'native_prompts':True,'reranker':'disabled for initial declared design'},
        'embedding_model_files_sha256':vector['model_files_sha256'],'released_wheel_sha256':file_hash(released_root/'lightrag_hku-1.5.7-py3-none-any.whl'),
        'label_policy':'Independent source-supported raw correctness 0/1/2, divide by 2 with raw score retained; no model-filled gold',
        'statistical_unit':'question; repeats averaged within question; full grid and explicit failures required',
        'online_api_scenario':budget(45,5,len(METHODS)),
        'blocking_conditions':['independent_gold_missing','full_released_index_missing','common_tokenizer_not_locked',
            'all_method_adapters_not_verified','index_and_query_budget_not_available','new_protocol_generation_logs_missing'],
        'actual_api_calls':0}
    output.mkdir(parents=True)
    atomic_json(output/'design.json',plan);atomic_json(output/'annotation_readiness.json',labels)
    with (output/'planned_run_grid.jsonl').open('w',encoding='utf-8') as stream:
        for method,qid,repeat in itertools.product(METHODS+['released_lightrag_1_5_7'],range(1,46),range(1,6)):
            stream.write(json.dumps({'method':method,'question_id':qid,'repeat':repeat,'state':'planned_not_executed'})+'\n')
    atomic_json(output/'analysis_design_controlled.json',{k:plan['controlled_track'][k] for k in ('methods','question_ids','repeats','reference','metrics')})
    atomic_json(output/'readiness.json',{'design_sha256':canonical_hash(plan),'ready_for_paid_batch':False,
        'ready_for_confirmatory_reporting':False,'planned_answers':2025,'planned_independent_answer_ratings_if_double_judged':4050,
        'blocking_conditions':plan['blocking_conditions'],'actual_api_calls':0})
    return plan


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('dataset','annotation','vector-run','released-root','output'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args();plan=prepare(**vars(args));print('Plan saved, blocked. Online scenario:',plan['online_api_scenario']['online_scenario_calls'],'calls; actual calls: 0')
