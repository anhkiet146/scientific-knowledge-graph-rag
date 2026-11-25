"""Offline validation replay; never overwrite or approve the original pilot."""
import argparse
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from workflow_io import read_json,loads,atomic_json,canonical_hash,file_hash
from reextract_review import sections_from_document
from chunk_contract import evaluate_bounded_task
from chunk_runner import verify_task,contract


def replay(source):
    manifest=read_json(source/'manifest.json');rows=[]
    for entry in manifest['sources']:
        sections=sections_from_document(read_json(source/'sources'/entry['file']))
        catalog=read_json(source/'catalogs'/entry['file'])
        for receipt in sorted((source/'tasks'/entry['paper_key']).glob('*/receipt.json')):
            folder=receipt.parent;original=verify_task(folder);raw=read_json(folder/'response.json')
            try:
                if raw['metadata'].get('finish_reason')!='STOP':raise ValueError('Truncated response')
                accepted,issues,blockers,child=evaluate_bounded_task(loads(raw['text']),read_json(folder/'spec.json'),
                    catalog,sections,manifest['policy']['max_continuation_depth'],manifest['policy']['max_metrics_per_task'])
            except (ValueError,TypeError,KeyError,AttributeError) as exc:
                accepted={'entities':[],'relations':[]};issues=[{'reason':'invalid_task_response','error':str(exc)}];blockers=[];child=None
            rows.append({'paper_key':entry['paper_key'],'task_id':folder.name,'receipt_sha256':file_hash(receipt),
                'original_retained_entities':len(original['extraction_result']['entities']),
                'original_retained_relations':len(original['extraction_result']['relations']),
                'replayed_result':accepted,'validation_issues':issues,'blocking_issues':blockers,
                'continuation':child,'candidate_status':'quarantined' if issues else 'pending_semantic_review'})
    policy,_=contract()
    return {'purpose':'Offline development replay; not a new model run or independent evaluation',
        'original_manifest_sha256':file_hash(source/'manifest.json'),'current_policy_sha256':canonical_hash(policy),
        'actual_api_calls':0,'graph_writes':0,'approved_for_graph':0,'tasks':rows}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();atomic_json(args.output,replay(args.run.resolve()))
