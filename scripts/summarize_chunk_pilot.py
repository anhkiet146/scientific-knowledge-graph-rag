"""Summarize receipts and validation failures without changing pilot artifacts."""
import argparse
from collections import Counter
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from workflow_io import read_json,atomic_json,file_hash
from chunk_runner import verify_task


def summarize(source):
    tasks=[];usage=Counter()
    for path in sorted((source/'tasks').glob('*/*/receipt.json')):
        result=verify_task(path.parent);response=read_json(path.parent/'response.json')
        raw=response.get('service_response') or {}
        for field,value in raw.get('usageMetadata',{}).items():
            if isinstance(value,int) and not isinstance(value,bool):usage[field]+=value
        reasons=Counter(i['reason'] for i in result['validation_issues'])
        details=Counter(d for i in result['validation_issues'] for d in i.get('details',[]))
        tasks.append({'paper_key':path.parent.parent.name,'task_id':result['task_id'],
            'finish_reason':response['metadata'].get('finish_reason'),'status':result['status'],
            'retained_entities':len(result['extraction_result']['entities']),
            'retained_relations':len(result['extraction_result']['relations']),
            'issue_reasons':dict(reasons),'issue_details':dict(details),
            'receipt_sha256':file_hash(path)})
    return {'source_run':str(source),'manifest_sha256':file_hash(source/'manifest.json'),
        'progress':read_json(source/'progress.json'),'tasks':tasks,'usage_totals':dict(usage),
        'actual_response_count':len(tasks),'graph_writes':0,
        'limitations':['Retained records are not semantically approved.',
            'Two task responses do not constitute two fully extracted papers.',
            'No independent gold scoring or scientific completeness claim.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();atomic_json(args.output,summarize(args.run.resolve()))
