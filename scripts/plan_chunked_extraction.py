"""Offline planning only: bound evidence per task; never calls a model or merges results."""
import argparse,json,re,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from reextract_review import sections_from_document
from evidence_catalog import build_catalog
from workflow_io import read_json,atomic_json,file_hash,canonical_hash


from task_plan import plan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--max-items',type=int,default=100);args=parser.parse_args()
    if args.input.resolve()==args.output.resolve():raise ValueError('Use a separate output directory')
    args.output.mkdir(parents=True,exist_ok=True);rows=[]
    for source in sorted(args.input.glob('*.json')):
        if source.name.startswith('_'):continue
        result=plan(read_json(source),args.max_items);result['source_sha256']=file_hash(source)
        atomic_json(args.output/source.name,result)
        rows.append({'file':source.name,'tasks':len(result['tasks']),'evidence_items':len(result['catalog']['items'])})
    atomic_json(args.output/'_summary.json',{'status':'proposal_only','actual_api_calls':0,'documents':rows,
                'planned_initial_api_calls':sum(r['tasks'] for r in rows),'no_execution_authorized_by_this_plan':True})
    print(json.dumps(rows))


if __name__=='__main__':main()
