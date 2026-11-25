"""Verify coordinate evidence against its PDF before producing pending candidates."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from workflow_io import read_json,canonical_hash,atomic_json,file_hash
from table_evidence import extract_table
from table_measurements import build_candidates


def prepare(pdf,spec_path,evidence_path):
    spec=read_json(spec_path);evidence=read_json(evidence_path)
    regenerated=extract_table(pdf,spec)
    if canonical_hash(evidence)!=canonical_hash(regenerated):raise ValueError('Evidence changed or belongs to another extractor; regenerate in a new directory')
    result=build_candidates(evidence)
    result['measurement_parser_sha256']=file_hash(ROOT/'src/extraction/table_measurements.py')
    result['verified_pdf_and_cell_mapping']=True
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',type=Path,required=True);parser.add_argument('--spec',type=Path,required=True)
    parser.add_argument('--evidence',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or args.output.resolve() in {p.resolve() for p in (args.pdf,args.spec,args.evidence)}:
        raise ValueError('Fresh candidate output required')
    atomic_json(args.output,prepare(args.pdf,args.spec,args.evidence))
