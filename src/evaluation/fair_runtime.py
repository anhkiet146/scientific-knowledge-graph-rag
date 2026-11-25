"""Shared CPU and dense-store conditions for controlled retrieval experiments."""
from contextlib import contextmanager
import importlib.metadata
import os
import platform
import asyncio
import time


def shared_embedding_callback(model,receipts):
    if str(model.device)!='cpu':raise ValueError('Shared embedding model must use CPU')
    async def embed(texts):
        import numpy as np
        from threadpoolctl import threadpool_info
        if any(p['num_threads']>4 for p in threadpool_info()):raise RuntimeError('Embedding outside controlled CPU context')
        prepared,audit=clip_embedding_inputs(model.tokenizer,texts,model.max_seq_length)
        start=time.perf_counter()
        matrix=await asyncio.to_thread(model.encode,prepared,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)
        if matrix.shape!=(len(texts),384) or not np.isfinite(matrix).all() or not np.allclose(np.linalg.norm(matrix,axis=1),1,atol=1e-4):
            raise ValueError('Embedding output violates shared dense contract')
        receipts.append({'inputs':len(texts),'truncated':sum(r['truncated'] for r in audit),
                         'max_tokens_after':max((r['tokens_after_with_special'] for r in audit),default=0),
                         'seconds':time.perf_counter()-start,'clipping_audit':audit})
        return matrix
    return embed


def clip_embedding_inputs(tokenizer,texts,max_sequence_length):
    if type(max_sequence_length) is not int or max_sequence_length<1:raise ValueError('Positive encoder limit required')
    budget=max_sequence_length-tokenizer.num_special_tokens_to_add(pair=False)
    if budget<1:raise ValueError('Encoder limit cannot fit text')
    clipped=[];audit=[]
    for index,text in enumerate(texts):
        if not isinstance(text,str):raise ValueError('Embedding inputs must be strings')
        before=tokenizer(text,add_special_tokens=False,truncation=False)['input_ids']
        value=tokenizer.decode(before[:budget],skip_special_tokens=False,clean_up_tokenization_spaces=False)
        after=tokenizer(value,add_special_tokens=True,truncation=False)['input_ids']
        if len(after)>max_sequence_length:raise ValueError('Tokenizer roundtrip exceeds encoder limit')
        clipped.append(value)
        audit.append({'input_index':index,'tokens_before_without_special':len(before),
                      'tokens_after_with_special':len(after),'truncated':len(before)>budget})
    return clipped,audit


@contextmanager
def controlled_cpu(threads=4):
    if type(threads) is not int or threads<1:raise ValueError('Positive thread count required')
    from threadpoolctl import threadpool_limits,threadpool_info
    import torch
    previous=torch.get_num_threads()
    torch.set_num_threads(threads)
    try:
        with threadpool_limits(limits=threads):
            pools=threadpool_info()
            if any(p['num_threads']>threads for p in pools):raise RuntimeError('CPU thread limit not applied')
            receipt={'platform':platform.platform(),'machine':platform.machine(),'processor':platform.processor(),
                   'logical_cpus':os.cpu_count(),'device':'cpu','torch_threads':torch.get_num_threads(),
                   'thread_pools':pools,'thread_limit':threads}
            yield receipt
            receipt['thread_pools_after']=threadpool_info()
            if any(p['num_threads']>threads for p in receipt['thread_pools_after']):
                raise RuntimeError('Late-loaded thread pool exceeds shared CPU limit')
    finally:torch.set_num_threads(previous)


def light_rag_parameters(protocol):
    dense=protocol['dense_conditions']
    if dense['backend']!='nano-vectordb==0.0.4.3' or dense['metric']!='cosine':
        raise ValueError('Unsupported shared vector backend')
    if dense['dimension']!=384 or dense['device']!='cpu' or dense['normalize'] is not True:
        raise ValueError('Dense runtime conditions differ')
    if importlib.metadata.version('nano-vectordb')!='0.0.4.3':raise ValueError('Vector backend version differs')
    if importlib.metadata.version('lightrag-hku')!='1.5.7':raise ValueError('Released LightRAG version differs')
    return {'vector_storage':'NanoVectorDBStorage',
            'enable_llm_cache':False,'enable_llm_cache_for_entity_extract':True,
            'embedding_cache_config':{'enabled':False,'similarity_threshold':0.95,'use_llm_check':False},
            'vector_db_storage_cls_kwargs':{'cosine_better_than_threshold':dense['threshold']},
            'graph_storage':'NetworkXStorage','kv_storage':'JsonKVStorage','doc_status_storage':'JsonDocStatusStorage',
            'chunk_token_size':256,'chunk_overlap_token_size':0,
            'entity_extract_max_gleaning':0,'llm_model_max_async':1,'embedding_func_max_async':1}
