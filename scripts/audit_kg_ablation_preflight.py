"""Audit KG ablation context artifacts; no annotation or QA quality estimates."""
import argparse
from pathlib import Path
import json
import os
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from workflow_io import read_json,canonical_hash,atomic_json


def audit(root,cache):
    os.environ['TIKTOKEN_CACHE_DIR']=str(cache.resolve())
    import tiktoken
    enc=tiktoken.get_encoding('o200k_base')
    rows=[json.loads(s) for s in (root/'all_eight_methods.jsonl').read_text(encoding='utf-8').split('\n') if s]
    methods=('bm25','vector','kg','kg_no_expansion','kg_raw','kg_no_semantic','kg_no_relation','kg_verified')
    grid={}
    for row in rows:
        key=(row['question_id'],row['method'])
        if key in grid:raise ValueError('Duplicate question/method')
        grid[key]=row
        text=json.dumps(row['context'],ensure_ascii=False,sort_keys=True,separators=(',',':'))
        if (text!=row['context_json'] or canonical_hash(text)!=row['context_sha256']
            or len(enc.encode(text,disallowed_special=()))!=row['context_tokens'] or row['context_tokens']>2000):
            raise ValueError('Invalid context serialization/hash/budget')
        if row['generation_status']!='not_executed' or row['quality_score'] is not None:raise ValueError('Unexpected answer/quality result')
        if row['method']=='kg_no_expansion' and any(c.get('connections') or c.get('degree') or c.get('hop_distance') for c in row['context']):
            raise ValueError('Graph neighborhood leak')
    if set(grid)!={(q,m) for q in range(1,46) for m in methods}:raise ValueError('Incomplete 45 x 8 grid')
    def identity(row):return [(c.get('entity_type'),c.get('entity_name'),tuple(c.get('source_papers',[]))) for c in row['context']]
    differences={}
    for method in methods[3:]:
        differences[method]=sum(identity(grid[q,method])!=identity(grid[q,'kg']) for q in range(1,46))
    for q in range(1,46):
        if grid[q,'kg']['context_json']!=grid[q,'kg_verified']['context_json']:raise ValueError('Verified retrieval must equal KG before verification')
    return {'status':'passed','rows':len(rows),'questions':45,'methods':len(methods),'no_expansion_degree_connections_hops_zero':True,
        'max_context_tokens':max(r['context_tokens'] for r in rows),'empty_contexts_by_method':{m:sum(not grid[q,m]['context'] for q in range(1,46)) for m in methods},
        'selected_identity_order_differs_from_kg_question_counts':differences,'actual_api_calls':0,'quality_scores_computed':False,
        'interpretation':'Selection/order differences are execution diagnostics, not recall, QA gains or significance. kg_verified has no verification execution yet.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('run','cache','output'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Fresh report required')
    atomic_json(args.output,audit(args.run,args.cache))
