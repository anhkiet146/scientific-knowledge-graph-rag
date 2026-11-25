"""Run the pinned released LightRAG on one development excerpt, never a QA benchmark."""
import argparse
import asyncio
import importlib.metadata
import os
import shutil
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/evaluation')]
from workflow_io import read_json,atomic_json,canonical_hash,file_hash
from strict_runner import _key
from budgeted_gemini_text import BudgetedText


async def run(args):
    if importlib.metadata.version('lightrag-hku')!='1.5.7':raise ValueError('Pinned LightRAG 1.5.7 required')
    output=args.output.resolve()
    if output.exists():raise ValueError('Fresh isolated smoke output required')
    document=read_json(args.source);abstract=document.get('abstract')
    if not isinstance(abstract,str) or not abstract.strip():raise ValueError('Development source abstract required')
    # No gold, QA references, or model-generated extraction is injected.
    excerpt=' '.join(abstract.split()[:100])
    output.mkdir(parents=True);atomic_json(output/'source_snapshot.json',document)
    atomic_json(output/'input.json',{'source_sha256':file_hash(args.source),'excerpt':excerpt,
        'excerpt_sha256':canonical_hash(excerpt),'scope':'first 100 abstract words of one development paper, not a full paper'})
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1';os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    os.environ['TIKTOKEN_CACHE_DIR']=str(output/'tokenizer_cache')
    import torch
    from sentence_transformers import SentenceTransformer
    from lightrag import LightRAG,QueryParam
    from lightrag.utils import EmbeddingFunc
    torch.set_num_threads(4)
    model=SentenceTransformer(str(args.model.resolve()),device='cpu',local_files_only=True,trust_remote_code=False)
    prior_files={}
    if args.existing_index:
        source_index=args.existing_index.resolve()
        prior_manifest=read_json(source_index.parent/'manifest.json')
        if prior_manifest['release']!='1.5.7' or prior_manifest['source_sha256']!=file_hash(args.source):
            raise ValueError('Existing index does not match development source/release')
        prior_files={p.relative_to(source_index).as_posix():file_hash(p) for p in sorted(source_index.rglob('*')) if p.is_file()}
        if not prior_files:raise ValueError('No existing index')
        shutil.copytree(source_index,output/'storage')
        if any(file_hash(output/'storage'/name)!=digest or file_hash(source_index/name)!=digest for name,digest in prior_files.items()):
            raise ValueError('Index changed while cloning')
    provider=BudgetedText('disabled-in-retrieval-only-recovery' if args.existing_index else _key(args),
        output/'provider_journal',max_calls=0 if args.existing_index else 2)
    async def llm(prompt,**kwargs):
        return await provider(prompt,**kwargs)
    embedding_calls=[]
    async def embed(texts):
        counts=[len(model.tokenizer(t,add_special_tokens=True)['input_ids']) for t in texts]
        start=time.perf_counter()
        result=await asyncio.to_thread(model.encode,texts,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)
        embedding_calls.append({'n_texts':len(texts),'texts_sha256':canonical_hash(texts),'token_counts':counts,
            'truncated_text_count':sum(n>model.max_seq_length for n in counts),'seconds':time.perf_counter()-start})
        return result
    parameters={'entity_extract_max_gleaning':0,'llm_model_max_async':1,'embedding_func_max_async':1,
        'chunk_token_size':256,'chunk_overlap_token_size':0,'kv_storage':'JsonKVStorage',
        'vector_storage':'NanoVectorDBStorage','graph_storage':'NetworkXStorage','doc_status_storage':'JsonDocStatusStorage'}
    manifest={'protocol_id':'released-lightrag-development-smoke-v1','release':'1.5.7','upstream':'https://github.com/HKUDS/LightRAG',
        'source_sha256':file_hash(args.source),'model_files_sha256':{p.relative_to(args.model).as_posix():file_hash(p) for p in sorted(args.model.rglob('*')) if p.is_file()},
        'parameters':parameters,'llm_model':'gemini-2.5-flash','max_api_calls':provider.maximum,
        'recovered_index_files_sha256':prior_files,
        'code_sha256':{p.name:file_hash(p) for p in [Path(__file__),Path(__file__).with_name('budgeted_gemini_text.py')]},
        'fairness_limits':'One development excerpt, native LightRAG prompts and ontology, explicit diagnostic query keywords. Not the frozen 482-paper/45-question benchmark or a generator-matched comparison.'}
    if args.existing_index and prior_manifest['model_files_sha256']!=manifest['model_files_sha256']:
        raise ValueError('Recovered index embedding model differs from selected local model')
    atomic_json(output/'manifest.json',manifest)
    rag=LightRAG(working_dir=str(output/'storage'),workspace='review_dev_v157',llm_model_func=llm,
        llm_model_name='gemini-2.5-flash',embedding_func=EmbeddingFunc(embedding_dim=384,func=embed,
        model_name='all-MiniLM-L6-v2-local'),**parameters)
    state='initializing';results=[]
    try:
        await rag.initialize_storages();state='indexing'
        if not args.existing_index:
            await rag.ainsert(excerpt,ids='development-rice-abstract-excerpt',file_paths='source_snapshot.json:abstract:first100words')
        statuses=await rag.doc_status.get_docs_by_statuses([__import__('lightrag.base',fromlist=['DocStatus']).DocStatus.PROCESSED],strict=True)
        atomic_json(output/'processed_documents.json',{k:vars(v) if hasattr(v,'__dict__') else v for k,v in statuses.items()})
        if not statuses:raise RuntimeError('No document reached processed status')
        state='retrieving'
        query='Which deep learning methods are used for rice leaf disease detection?'
        for mode in ('hybrid','naive'):
            before=provider.calls;start=time.perf_counter()
            result=await rag.aquery_data(query,param=QueryParam(mode=mode,top_k=8,chunk_top_k=8,
                max_total_tokens=2000,enable_rerank=False,hl_keywords=['rice leaf disease detection'],ll_keywords=['MobileNet','ResNet']))
            results.append({'mode':mode,'result':result,'seconds':time.perf_counter()-start,'additional_llm_calls':provider.calls-before})
            if result.get('status')!='success' or not result.get('data',{}).get('chunks'):
                raise RuntimeError('Released retrieval returned no successful chunk context')
        atomic_json(output/'retrieval_results.json',results);state='smoke_complete'
    except Exception as exc:
        atomic_json(output/'failure.json',{'stage':state,'exception_type':type(exc).__name__,
            'message':str(exc).replace(provider.key,'[REDACTED]')[:1000]});state='failed'
    finally:
        await rag.finalize_storages()
        if args.existing_index and any(file_hash(args.existing_index/name)!=digest for name,digest in prior_files.items()):
            raise ValueError('Original index changed during recovery')
        atomic_json(output/'embedding_calls.json',embedding_calls)
        atomic_json(output/'summary.json',{'status':state,'release':'1.5.7','reserved_api_calls':provider.calls,
            'n_query_modes':len(results),'scope':'one development abstract excerpt','quality_scores_computed':False,
            'production_graph_writes':0,'native_lightRAG_test_storage_created':True,
            'limitations':'A smoke test of the official release, not a SOTA performance comparison or approved extraction.'})
    print('LightRAG development smoke:',state,'API calls:',provider.calls,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--keys-file',type=Path,required=True)
    parser.add_argument('--existing-index',type=Path)
    asyncio.run(run(parser.parse_args()))
