"""Initialize official LightRAG under shared conditions, with all LLM calls disabled."""
import argparse
import asyncio
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/evaluation')]
from workflow_io import read_json,atomic_json,file_hash,canonical_hash
from fair_runtime import controlled_cpu,light_rag_parameters,shared_embedding_callback


async def run(protocol,model_manifest,chunk_plan,tokenizer_cache,output):
    if output.exists():raise ValueError('Fresh output required')
    settings=read_json(protocol);pin=read_json(model_manifest);model_path=Path(pin['model_path'])
    if canonical_hash(pin['model_files_sha256'])!=settings['dense_conditions']['model_files_sha256']:raise ValueError('Model pin differs')
    for name,digest in pin['model_files_sha256'].items():
        if file_hash(model_path/name)!=digest:raise ValueError('Model files changed')
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',TIKTOKEN_CACHE_DIR=str(tokenizer_cache.resolve()))
    import tiktoken.load
    def offline(url):raise RuntimeError('Tokenizer download disabled')
    tiktoken.load.read_file=offline
    from sentence_transformers import SentenceTransformer
    from lightrag import LightRAG
    from lightrag.utils import EmbeddingFunc
    import json
    plan=read_json(chunk_plan/'manifest.json')
    if file_hash(chunk_plan/'chunks.jsonl')!=plan['chunk_file_sha256']:raise ValueError('Chunk plan changed')
    chunks=[json.loads(s) for s in (chunk_plan/'chunks.jsonl').read_text(encoding='utf-8').splitlines()]
    short=next(r['content'] for r in chunks if r['embedding_tokens_before_clipping']<=256)
    long=next(r['content'] for r in chunks if r['embedding_tokens_before_clipping']>256)
    output.mkdir(parents=True);calls=[];embedding_receipts=[]
    async def disabled_llm(*args,**kwargs):
        calls.append('blocked');raise RuntimeError('LLM disabled in runtime check')
    with controlled_cpu(4) as runtime:
        model=SentenceTransformer(str(model_path),device='cpu',local_files_only=True,trust_remote_code=False)
        embed=shared_embedding_callback(model,embedding_receipts)
        vectors=await embed([short,long])
        rag=LightRAG(working_dir=str(output/'storage'),workspace='fair488_runtime_only',
            llm_model_func=disabled_llm,llm_model_name='gemini-2.5-flash',
            embedding_func=EmbeddingFunc(embedding_dim=384,func=embed,model_name='all-MiniLM-L6-v2-local'),
            **light_rag_parameters(settings))
        try:
            await rag.initialize_storages()
            actual={name:{'class':type(getattr(rag,name)).__name__,
                          'threshold':getattr(getattr(rag,name),'cosine_better_than_threshold',None)}
                    for name in ['entities_vdb','relationships_vdb','chunks_vdb']}
            if any(v['class']!='NanoVectorDBStorage' or v['threshold']!=-1.0 for v in actual.values()):raise ValueError('Official vector store settings differ')
            cache_conditions={'online_llm_cache':rag.enable_llm_cache,
                              'query_embedding_cache':rag.embedding_cache_config['enabled'],
                              'index_extraction_resume_cache':rag.enable_llm_cache_for_entity_extract}
            if cache_conditions!={'online_llm_cache':False,'query_embedding_cache':False,'index_extraction_resume_cache':True}:
                raise ValueError('Online cache conditions differ')
        finally:await rag.finalize_storages()
    atomic_json(output/'runtime.json',runtime)
    atomic_json(output/'embedding_receipts.json',embedding_receipts)
    atomic_json(output/'summary.json',{'state':'runtime_initialized_not_indexed','official_implementation':'LightRAG 1.5.7',
        'actual_vector_stores':actual,'embedding_shape':list(vectors.shape),'llm_callbacks':len(calls),
        'cache_conditions':cache_conditions,
        'api_calls':0,'documents_indexed':0,'quality_scores_computed':False,'embedding_model_files_sha256':pin['model_files_sha256'],
        'protocol_sha256':file_hash(protocol),'code_sha256':file_hash(Path(__file__)),
        'runtime_code_sha256':file_hash(ROOT/'src/evaluation/fair_runtime.py'),
        'limits':'Two genuine local embeddings and empty official storage initialization; no corpus indexing, extraction or retrieval/QA performance measurement.'})
    print('Official LightRAG stores verified; local embeddings:',list(vectors.shape),'API calls:0',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('protocol','model-manifest','chunk-plan','tokenizer-cache','output'):parser.add_argument('--'+name,type=Path,required=True)
    asyncio.run(run(**vars(parser.parse_args())))
