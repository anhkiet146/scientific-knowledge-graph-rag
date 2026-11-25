"""Audit actual released-package artifacts; never score extraction or QA quality."""
import argparse
import hashlib
import importlib.metadata
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from workflow_io import read_json,file_hash,atomic_json


def audit(root):
    metadata=read_json(root/'pypi_metadata.json');wheel=root/'lightrag_hku-1.5.7-py3-none-any.whl'
    expected=next(u['digests']['sha256'] for u in metadata['urls'] if u['filename']==wheel.name)
    if file_hash(wheel)!=expected:raise ValueError('Release wheel differs from PyPI metadata')
    if importlib.metadata.version('lightrag-hku')!='1.5.7':raise ValueError('Wrong installed release')
    dist=importlib.metadata.distribution('lightrag-hku');checked=[]
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith('lightrag/') and name.endswith('.py'):
                target=Path(dist.locate_file(name))
                if file_hash(target)!=hashlib.sha256(archive.read(name)).hexdigest():raise ValueError('Installed upstream code differs from wheel')
                checked.append(name)
    recovery=root/'retrieval_recovery';manifest=read_json(recovery/'manifest.json')
    original=root/'live_development_smoke'/'storage'
    if any(file_hash(original/name)!=digest for name,digest in manifest['recovered_index_files_sha256'].items()):
        raise ValueError('Original released index changed')
    source_manifest=read_json(root/'live_development_smoke'/'manifest.json')
    if source_manifest['model_files_sha256']!=manifest['model_files_sha256']:raise ValueError('Embedding mismatch')
    graph=ET.parse(original/'review_dev_v157/graph_chunk_entity_relation.graphml')
    ns={'g':'http://graphml.graphdrawing.org/xmlns'}
    nodes=len(graph.findall('.//g:node',ns));edges=len(graph.findall('.//g:edge',ns))
    responses=list((root/'live_development_smoke/provider_journal').glob('*/response.json'))
    recovery_responses=list((recovery/'provider_journal').glob('*/response.json'))
    if len(responses)!=1 or recovery_responses:raise ValueError('Unexpected API call accounting')
    raw=read_json(responses[0]);results=read_json(recovery/'retrieval_results.json')
    if raw['candidates'][0]['finishReason']!='STOP':raise ValueError('Incomplete indexing response')
    chunks=read_json(original/'review_dev_v157/kv_store_text_chunks.json')
    counts=[]
    if {r['mode'] for r in results}!={'hybrid','naive'} or len(results)!=2:raise ValueError('Query modes incomplete')
    for row in results:
        result=row['result'];data=result.get('data',{})
        if result.get('status')!='success' or not data.get('chunks') or row['additional_llm_calls']!=0:
            raise ValueError('Retrieval did not complete without additional LLM')
        for c in data['chunks']:
            if c['chunk_id'] not in chunks or c['content']!=chunks[c['chunk_id']]['content']:
                raise ValueError('Retrieved chunk differs from source index')
        counts.append({'mode':row['mode'],'entities':len(data.get('entities',[])),
            'relationships':len(data.get('relationships',[])),'chunks':len(data['chunks'])})
    return {'status':'passed','release':'1.5.7','upstream_python_files_verified':len(checked),'graph_nodes':nodes,
        'graph_edges':edges,'indexing_api_responses':len(responses),'retrieval_api_responses':0,
        'indexing_usage':raw.get('usageMetadata',{}),'retrieval':counts,'original_index_unchanged':True,
        'quality_scores_computed':False,'production_graph_writes':0,
        'interpretation':'Official-release integration smoke on one excerpt; not a full-corpus SOTA comparison.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Fresh audit report required')
    atomic_json(args.output,audit(args.root))
