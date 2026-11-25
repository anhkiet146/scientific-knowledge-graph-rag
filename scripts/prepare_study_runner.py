"""Prepare a complete frozen-context runner contract; NEVER invoke a provider."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/evaluation'),str(ROOT/'src/extraction')]
from resumable_study import run_study,BASE_METHODS
from workflow_io import atomic_json,file_hash


def prepare(context_file,output):
    if output.exists():raise ValueError('Fresh study preparation output required')
    contexts=[json.loads(line) for line in context_file.read_text(encoding='utf-8').split('\n') if line]
    keys=[(r['question_id'],r['method']) for r in contexts]
    if len(keys)!=360 or set(keys)!={(q,m) for q in range(1,46) for m in (*BASE_METHODS,'kg_verified')}:raise ValueError('45 x 8 grid required')
    summary=asyncio.run(run_study(contexts,output,provider=None,max_calls=0,repeats=5))
    atomic_json(output/'preparation.json',{'mode':'offline_no_provider','actual_api_calls':0,'expected_generation_or_verification_jobs':1800,
        'contexts_file':str(context_file.resolve()),'contexts_sha256':file_hash(context_file),
        'contract_sha256':file_hash(output/'contract.json'),'engine':str((ROOT/'src/evaluation/resumable_study.py').resolve()),
        'limits':'No live adapter configured. API budget approval and provider configuration required separately. No SOTA indexing or quality scores fabricated.'})
    print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--contexts',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prepare(a.contexts,a.output)
