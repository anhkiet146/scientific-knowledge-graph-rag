import argparse
import asyncio
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/evaluation'),str(ROOT/'src/normalization')]
from alias_advisory import prompt,materialize
from budgeted_gemini_text import BudgetedText
from strict_runner import _key
from workflow_io import read_json,loads,atomic_json,file_hash


async def run(args):
    if args.output.exists():raise ValueError('Fresh output required')
    cases=read_json(args.cases)
    if len(cases)!=2:raise ValueError('Two pilot cases required')
    for case in cases:
        pdf=args.pdfs/(Path(case['paper']).stem+'.pdf')
        if file_hash(pdf)!=case['pdf_sha256']:raise ValueError('PDF changed')
    args.output.mkdir(parents=True)
    atomic_json(args.output/'cases.json',cases)
    source=ROOT/'src/normalization/alias_advisory.py'
    (args.output/'alias_advisory_snapshot.py').write_bytes(source.read_bytes())
    atomic_json(args.output/'manifest.json',{'cases_sha256':file_hash(args.cases),'code_sha256':file_hash(Path(__file__)),
        'advisory_code_sha256':file_hash(source),'model':'gemini-2.5-flash','temperature':0,'thinking_budget':0,
        'max_output_tokens':1536,'max_api_calls':2,'auto_merge':False})
    provider=BudgetedText(_key(args),args.output/'provider_journal',max_calls=2,max_output_tokens=1536,requests_per_minute=4)
    proposals=[];stop=None
    for case in cases:
        request=prompt(case);atomic_json(args.output/(case['candidate_id']+'_prompt.json'),{'prompt':request})
        try:
            response=await provider(request,json_mode=True)
            verdict=loads(response);atomic_json(args.output/(case['candidate_id']+'_verdict.json'),verdict)
            proposal=materialize(verdict,case)
        except Exception as exc:
            stop='provider_or_validation_failure_no_retry'
            atomic_json(args.output/'failure.json',{'state':stop,'candidate_id':case['candidate_id'],'error_type':type(exc).__name__})
            break
        proposals.append(proposal);atomic_json(args.output/(case['candidate_id']+'_proposal.json'),proposal)
        print(case['candidate_id'],proposal['decision'],flush=True)
    atomic_json(args.output/'summary.json',{'status':stop or 'pilot_complete','reserved_api_calls':provider.calls,
        'proposals_validated':len(proposals),'decisions':[p['decision'] for p in proposals],
        'graph_merges_applied':0,'quality_scores_computed':False,'independent_gold':False})


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for flag in ('cases','pdfs','output','keys-file'):p.add_argument('--'+flag,type=Path,required=True)
    asyncio.run(run(p.parse_args()))
