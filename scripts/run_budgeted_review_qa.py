import argparse
import asyncio
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/evaluation')]
from workflow_io import read_json,loads,atomic_json,file_hash
from resumable_study import run_study
from budgeted_gemini_text import BudgetedText
from strict_runner import _key


async def run(args):
    if type(args.max_api_calls) is not int or not 0<=args.max_api_calls<=16:raise ValueError('Pilot budget range is 0..16')
    if args.output.exists() and not args.resume:raise ValueError('Use fresh output or explicit resume')
    manifest=read_json(args.contexts.parent/'manifest.json')
    if file_hash(args.contexts)!=manifest['contexts_sha256']:raise ValueError('Prepared contexts changed')
    contexts=[loads(s) for s in args.contexts.read_text(encoding='utf-8').split('\n') if s]
    if len(contexts)!=360:raise ValueError('Complete prepared grid required')
    adapter_contract={'adapter_sha256':file_hash(ROOT/'src/evaluation/budgeted_gemini_text.py'),
        'launcher_sha256':file_hash(Path(__file__)),'contexts_sha256':file_hash(args.contexts),
        'model':'gemini-2.5-flash','temperature':0,'thinking_budget':0,'answer_output_tokens':1024,
        'verification_output_tokens':4096,'maximum_calls_per_segment':16,'requests_per_minute':4}
    contract_file=args.output/'live_adapter_contract.json'
    if args.resume and not contract_file.exists():raise ValueError('Legacy run lacks adapter binding; inspect before migration')
    if contract_file.exists() and read_json(contract_file)!=adapter_contract:raise ValueError('Adapter or launcher changed since run')
    args.output.mkdir(parents=True,exist_ok=True)
    if not contract_file.exists():atomic_json(contract_file,adapter_contract)
    snapshot=args.output/'launch_source';snapshot.mkdir(exist_ok=True)
    for source in [Path(__file__),ROOT/'src/evaluation/budgeted_gemini_text.py']:
        target=snapshot/source.name
        if target.exists() and file_hash(target)!=file_hash(source):raise ValueError('Launch snapshot mismatch')
        if not target.exists():target.write_bytes(source.read_bytes())
    provider=None
    if args.execute:
        if args.max_api_calls<1:raise ValueError('Explicit positive API budget required')
        segments=args.output/'provider_segments';segments.mkdir(parents=True,exist_ok=True)
        session=segments/f'{len(list(segments.iterdir()))+1:04d}'
        provider=BudgetedText(_key(args),session,max_calls=args.max_api_calls,scope='controlled_generation_pilot',
                              max_output_tokens=1024,requests_per_minute=4)
    summary=await run_study(contexts,args.output,provider=provider,max_calls=args.max_api_calls if args.execute else 0,repeats=5)
    print(summary)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for flag in ('contexts','output'):p.add_argument('--'+flag,type=Path,required=True)
    p.add_argument('--keys-file',type=Path);p.add_argument('--max-api-calls',type=int,default=0)
    p.add_argument('--execute',action='store_true');p.add_argument('--resume',action='store_true')
    asyncio.run(run(p.parse_args()))
