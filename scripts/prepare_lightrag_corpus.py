"""Prepare local full-corpus LightRAG inputs and config; no indexing or model calls."""
import argparse
from collections import defaultdict
import importlib.metadata
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/evaluation'),str(ROOT/'scripts')]
from snapshot_benchmark import load_chunks
from workflow_io import atomic_json,file_hash,canonical_hash
from prepare_review_dataset import verify


def prepare(dataset,vector,output):
    if output.exists():raise ValueError('Fresh output required')
    verify(dataset)
    if importlib.metadata.version('lightrag-hku')!='1.5.7':raise ValueError('Pinned LightRAG 1.5.7 required')
    config=json.loads((vector/'manifest.json').read_text(encoding='utf-8'))
    if config['dataset_manifest_sha256']!=file_hash(dataset/'manifest.json'):raise ValueError('Corpus mismatch')
    grouped=defaultdict(list)
    # One intact section per input record, not overlapping passage concatenation.
    for section in load_chunks(dataset/'corpus',chunk_size=10**9,overlap=0):grouped[section['paper_id']].append(section)
    if len(grouped)!=482:raise ValueError('Expected exactly 482 source documents')
    output.mkdir(parents=True);documents=output/'documents';documents.mkdir();records=[]
    for identifier,sections in sorted(grouped.items()):
        text='\n\n'.join('TITLE: '+s['title']+'\nSECTION: '+s['section']+'\n'+s['text'] for s in sections)
        name=canonical_hash(identifier)+'.txt';file=documents/name;file.write_text(text,encoding='utf-8')
        records.append({'paper_id':identifier,'file':'documents/'+name,'sha256':file_hash(file),'characters':len(text)})
    atomic_json(output/'manifest.json',{'state':'inputs_prepared_not_indexed','documents':records,
        'corpus_manifest_sha256':file_hash(dataset/'manifest.json'),'vector_manifest_sha256':file_hash(vector/'manifest.json'),
        'implementation':'LightRAG 1.5.7','embedding_model_path':config['model_path'],'embedding_model_files_sha256':config['model_files_sha256'],
        'embedding_device':'cpu','embedding_dimension':384,'normalization':'unit-normalized MiniLM, same cached weights as Vector',
        'generator':'gemini-2.5-flash','input_policy':'Same frozen parsed corpus; headers/metadata, abstracts and intact non-reference sections; no overlapping chunk duplication',
        'comparison_limits':'Native LightRAG whole-system track; native chunking, keyword stages and prompts differ. Preparation is not an executed SOTA comparison.',
        'actual_api_calls':0,'indexing_executed':False,'indexing_api_budget':None})
    verify(dataset);print('Prepared',len(records),'documents; model calls: 0; indexing not executed')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('dataset','vector','output'):p.add_argument('--'+flag,type=Path,required=True)
    prepare(**vars(p.parse_args()))
