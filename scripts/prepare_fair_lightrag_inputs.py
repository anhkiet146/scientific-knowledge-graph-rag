"""Freeze official LightRAG inputs from exactly the repaired comparison corpus."""
import argparse
from collections import defaultdict
import importlib.metadata
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src/evaluation'),str(ROOT/'src/extraction')]
from run_repaired_source_baselines import verify_source
from snapshot_benchmark import load_chunks
from workflow_io import read_json,atomic_json,file_hash,canonical_hash


def prepare(dataset,protocol,output):
    if output.exists():raise ValueError('Fresh output required')
    manifest=verify_source(dataset);settings=read_json(protocol)
    if file_hash(dataset/'manifest.json')!=settings['shared_inputs']['corpus_sha256']:
        raise ValueError('Comparison corpus mismatch')
    if importlib.metadata.version('lightrag-hku')!='1.5.7':raise ValueError('Pinned released LightRAG required')
    groups=defaultdict(list)
    for section in load_chunks(dataset/'corpus',chunk_size=10**9,overlap=0):groups[section['paper_id']].append(section)
    if len(groups)!=manifest['documents']:raise ValueError('Document identity/count mismatch')
    output.mkdir(parents=True);(output/'documents').mkdir();records=[]
    for identity,sections in sorted(groups.items()):
        text='\n\n'.join('TITLE: '+s['title']+'\nSECTION: '+s['section']+'\n'+s['text'] for s in sections)
        path=output/'documents'/(canonical_hash(identity)+'.txt');path.write_text(text,encoding='utf-8')
        records.append({'paper_id':identity,'path':path.relative_to(output).as_posix(),'sha256':file_hash(path)})
    verify_source(dataset)
    atomic_json(output/'manifest.json',{'state':'inputs_prepared_index_not_built','implementation':'LightRAG 1.5.7',
        'dataset_manifest_sha256':file_hash(dataset/'manifest.json'),'protocol_sha256':file_hash(protocol),
        'documents':records,'document_count':len(records),'dense_conditions':settings['dense_conditions'],
        'generation':settings['generation'],'query_sha256':settings['shared_inputs']['query_sha256'],
        'scope_policy':'whole_corpus','actual_api_calls':0,'indexing_executed':False,
        'code_sha256':file_hash(Path(__file__)),
        'limits':'Preparation only. Official extraction/index/query stages still require execution and accounting. Mixed historical parsed sections/PDF pages retained; page-level references not uniformly tagged. Native chunking differences disclosed; no quality or latency claims.'})
    print('Prepared',len(records),'LightRAG documents; index not built; API calls:0')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('dataset','protocol','output'):parser.add_argument('--'+name,type=Path,required=True)
    prepare(**vars(parser.parse_args()))
