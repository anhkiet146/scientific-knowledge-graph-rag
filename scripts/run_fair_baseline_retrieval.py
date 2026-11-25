"""Repeat both baselines under the same enforced CPU/store/context contract."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/evaluation'),str(ROOT/'src/extraction'),str(ROOT/'scripts')]
from workflow_io import atomic_json,read_json,file_hash,canonical_hash
from context_budget import pack_v2
from snapshot_benchmark import BM25Index
from run_repaired_source_baselines import verify_source
from fair_runtime import controlled_cpu,light_rag_parameters


def run(protocol,dataset,prior,cache,output):
    import numpy as np
    from nano_vectordb import NanoVectorDB
    if output.exists():raise ValueError('Fresh output required')
    settings=read_json(protocol);verify_source(dataset)
    if file_hash(dataset/'manifest.json')!=settings['shared_inputs']['corpus_sha256']:raise ValueError('Wrong corpus')
    m=read_json(prior/'manifest.json')
    if m['dataset_manifest_sha256']!=settings['shared_inputs']['corpus_sha256']:raise ValueError('Cache corpus differs')
    for name,field in [('contexts.jsonl','contexts_sha256'),('chunks.jsonl','chunks_sha256'),('embeddings.npy','embedding_sha256')]:
        if file_hash(prior/name)!=m[field]:raise ValueError('Cached index changed')
    dense=settings['dense_conditions'];light_parameters=light_rag_parameters(settings)
    if canonical_hash(m['model_files_sha256'])!=dense['model_files_sha256']:raise ValueError('Model pin differs')
    model_path=Path(m['model_path'])
    for name,digest in m['model_files_sha256'].items():
        if file_hash(model_path/name)!=digest:raise ValueError('Model files changed')
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',TIKTOKEN_CACHE_DIR=str(cache.resolve()))
    import tiktoken,tiktoken.load
    from sentence_transformers import SentenceTransformer
    def offline(url):raise RuntimeError('Tokenizer downloads disabled')
    tiktoken.load.read_file=offline;encoder=tiktoken.get_encoding('o200k_base')
    rows=[json.loads(s) for s in (prior/'contexts.jsonl').read_text(encoding='utf-8').splitlines()]
    cases={r['question_id']:(r['question'],r['shared_query']) for r in rows}
    if set(cases)!=set(range(1,46)):raise ValueError('45 cases required')
    if canonical_hash([(i,cases[i][0]) for i in sorted(cases)])!=settings['shared_inputs']['question_sha256']:raise ValueError('Question identity differs')
    if canonical_hash([(i,cases[i][1]) for i in sorted(cases)])!=settings['shared_inputs']['query_sha256']:raise ValueError('Shared query differs')
    chunks=[json.loads(s) for s in (prior/'chunks.jsonl').read_text(encoding='utf-8').splitlines()]
    matrix=np.load(prior/'embeddings.npy',allow_pickle=False)
    if matrix.shape!=(len(chunks),dense['dimension']) or not np.isfinite(matrix).all():raise ValueError('Invalid matrix')
    output.mkdir(parents=True);records={};timings=[]
    with controlled_cpu(dense['threads']) as runtime:
        model=SentenceTransformer(str(model_path),device='cpu',local_files_only=True,trust_remote_code=False)
        start=time.perf_counter();bm=BM25Index([c['shared_retrieval_text'] for c in chunks]);bm_build=time.perf_counter()-start
        store=NanoVectorDB(dense['dimension'],metric=dense['metric'],storage_file=str(output/'vectors.json'))
        start=time.perf_counter();store.upsert([{'__id__':str(i),'__vector__':v.copy()} for i,v in enumerate(matrix)]);store.save();vector_build=time.perf_counter()-start
        for repeat in range(1,settings['repeats']+1):
            for qid,(question,query) in sorted(cases.items()):
                for method in (['bm25','vector'] if (repeat+qid)%2 else ['vector','bm25']):
                    start=time.perf_counter();embed_seconds=0
                    if method=='vector':
                        t=time.perf_counter();q=model.encode([query],normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)[0];embed_seconds=time.perf_counter()-t
                        hits=[(int(h['__id__']),float(h['__metrics__'])) for h in store.query(q,top_k=8,better_than_threshold=dense['threshold'])]
                    else:hits=bm.search(query,8)
                    search_end=time.perf_counter()
                    context,text,count,audit=pack_v2([{**chunks[i]['source'],'chunk_id':i} for i,_ in hits],lambda t:encoder.encode(t,disallowed_special=()),2000)
                    end=time.perf_counter()
                    row={'question_id':qid,'question':question,'shared_query':query,'method':method,'context':context,
                         'context_json':text,'context_sha256':canonical_hash(text),'context_tokens':count,'quality_score':None}
                    key=(qid,method)
                    if key in records and records[key]['context_json']!=text:raise ValueError('Context changed across repeats')
                    records[key]=row
                    timings.append({'question_id':qid,'method':method,'repeat':repeat,'query_embedding_seconds':embed_seconds,
                                    'search_seconds':search_end-start-embed_seconds,'packing_seconds':end-search_end,
                                    'retrieval_wall_seconds':end-start,'context_sha256':row['context_sha256']})
            print('Completed repeat',repeat,'/',settings['repeats'],flush=True)
    path=output/'contexts.jsonl';path.write_text(''.join(json.dumps(records[k],ensure_ascii=False)+'\n' for k in sorted(records)),encoding='utf-8')
    atomic_json(output/'timings.json',timings)
    atomic_json(output/'runtime.json',runtime)
    atomic_json(output/'lightrag_runtime_parameters.json',light_parameters)
    verify_source(dataset)
    atomic_json(output/'manifest.json',{'state':'contexts_frozen','protocol_sha256':file_hash(protocol),
        'cache_policy':settings.get('cache_policy',{}),
        **settings['shared_inputs'],'dense':dense,'questions':45,'context_records':90,'repeats':settings['repeats'],
        'contexts_sha256':file_hash(path),'timings_sha256':file_hash(output/'timings.json'),
        'runtime_sha256':file_hash(output/'runtime.json'),'index_build_seconds':{'bm25':bm_build,'vector':vector_build},
        'index_lineage_manifest_sha256':file_hash(prior/'manifest.json'),'vector_store_sha256':file_hash(output/'vectors.json'),
        'code_sha256':file_hash(Path(__file__)),'api_calls':0,'quality_scores_computed':False,
        'runtime_code_sha256':file_hash(ROOT/'src/evaluation/fair_runtime.py'),
        'packing_code_sha256':file_hash(ROOT/'src/evaluation/context_budget.py'),
        'limits':'Warm retrieval repeated on one machine; index timings reuse cached corpus embeddings and exclude extraction/embedding build cost. No generation or KG/LightRAG performance comparison; runtime condition enforcement only.'})
    print('Saved90contexts and',len(timings),'retrieval timings; API calls:0',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('protocol','dataset','prior','cache','output'):p.add_argument('--'+name,type=Path,required=True)
    run(**vars(p.parse_args()))
