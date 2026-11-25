"""Verify source occurrence preservation, packed evidence, tokens and run pairing."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/normalization')]
from workflow_io import canonical_hash,atomic_json,file_hash
from normalize_entities import extraction_payload


def lines(path):return [json.loads(s) for s in path.read_text(encoding='utf-8').split('\n') if s]


def audit(folder,dataset,vector,cache):
    import tiktoken.load
    def no_network(*args,**kwargs):raise RuntimeError('Offline cache required')
    tiktoken.load.read_file=no_network;os.environ['TIKTOKEN_CACHE_DIR']=str(cache.resolve())
    import tiktoken
    enc=tiktoken.get_encoding('o200k_base')
    expected_entities=Counter();expected_relations=Counter();entities=set();relations=set();papers=set()
    for path in sorted((dataset/'extracted').glob('*.json')):
        document=json.loads(path.read_text(encoding='utf-8'));payload=extraction_payload(document)
        paper=document.get('filename',path.stem)
        papers.add(canonical_hash({'source_file':path.name,'paper_id':paper,'paper_title':document.get('paper_title',paper)}))
        for index,entity in enumerate(payload.get('entities',[])):
            expected_entities[canonical_hash({'file':path.name,'index':index,'entity':entity})]+=1
            entities.add(canonical_hash({'source_file':path.name,'paper_id':paper,'entity':entity}))
        for index,relation in enumerate(payload.get('relations',[])):
            expected_relations[canonical_hash({'file':path.name,'index':index,'relation':relation})]+=1
            relations.add(canonical_hash({'source_file':path.name,'paper_id':paper,'relation':relation}))
    actual_entities=Counter(canonical_hash(o) for node in lines(folder/'normalized_evidence_nodes.jsonl') for o in node['occurrences'])
    actual_relations=Counter(canonical_hash({k:r[k] for k in ('file','index','relation')}) for r in lines(folder/'normalized_evidence_relations.jsonl'))
    if actual_entities!=expected_entities or actual_relations!=expected_relations:raise ValueError('Lost or changed source occurrences')
    chunks={r['chunk_id']:{**r['source'],'chunk_id':r['chunk_id']} for r in lines(vector/'chunks.jsonl')}
    rows=lines(folder/'all_eight_methods.jsonl');grid={};checked=0
    methods=('bm25','vector','kg','kg_no_expansion','kg_raw','kg_no_semantic','kg_no_relation','kg_verified')
    for row in rows:
        key=row['question_id'],row['method']
        if key in grid:raise ValueError('Duplicate record')
        grid[key]=row
        text=json.dumps(row['context'],ensure_ascii=False,sort_keys=True,separators=(',',':'))
        if text!=row['context_json'] or canonical_hash(text)!=row['context_sha256'] or len(enc.encode(text,disallowed_special=()))!=row['context_tokens'] or row['context_tokens']>2000:
            raise ValueError('Invalid serialization, hash or token budget')
        for context in row['context']:
            if row['method'] in ('bm25','vector'):
                if context!=chunks[context['chunk_id']]:raise ValueError('Changed baseline source chunk')
            elif canonical_hash(context) not in entities|relations|papers:raise ValueError('Unscoped or modified graph evidence')
            if row['method']=='kg_no_expansion' and 'relation' in context:raise ValueError('Relation leaked into no-expansion context')
            checked+=1
    if set(grid)!={(q,m) for q in range(1,46) for m in methods}:raise ValueError('Incomplete grid')
    for q in range(1,46):
        if len({grid[q,m]['question'] for m in methods})!=1 or len({grid[q,m]['shared_query'] for m in methods})!=1:raise ValueError('Different query/question')
        if grid[q,'kg']['context_json']!=grid[q,'kg_verified']['context_json']:raise ValueError('Verification pair differs')
    # Known development case: presence in supplied evidence, not answer quality.
    names=['Tran Van Hau','Phan Van Ut','Phan Huynh Anh','Tran Sy Hieu']
    case={m:{name:name.casefold() in json.dumps(grid[1,m]['context'],ensure_ascii=False).casefold() for name in names} for m in ('kg','kg_raw')}
    result={'status':'passed','records':len(rows),'checked_context_items':checked,'entity_occurrences_preserved':sum(actual_entities.values()),
            'relation_occurrences_preserved':sum(actual_relations.values()),'source_objects_unchanged':True,'paired_contexts_identical':True,
            'max_tokens':max(r['context_tokens'] for r in rows),'known_development_case_name_presence':case,
            'actual_api_calls':0,'quality_scores_computed':False,'contexts_sha256':file_hash(folder/'all_eight_methods.jsonl'),
            'limits':'Checks source-object preservation, not extraction correctness, entailment, semantic recall or independent QA quality. Development case cannot support generalization.'}
    atomic_json(folder/'artifact_audit.json',result);print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('folder','dataset','vector','cache'):p.add_argument('--'+flag,type=Path,required=True)
    audit(**vars(p.parse_args()))
