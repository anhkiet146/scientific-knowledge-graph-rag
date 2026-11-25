"""Check a human review export against PDF-replayed pilot candidates."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from coordinate_review import load_context,validate_submission
from workflow_io import read_json,atomic_json,file_hash

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot',type=Path,required=True);parser.add_argument('--review',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists() or args.output.resolve().is_relative_to(args.pilot.resolve()):raise ValueError('Fresh report outside pilot required')
    template,rows=load_context(args.pilot)
    report=validate_submission(template,read_json(args.review),blocked_ids={rid for rid,(_,r,_) in rows.items() if r['status']=='blocked'})
    report['review_file_sha256']=file_hash(args.review);atomic_json(args.output,report)
    print(report['counts'])
