"""Measure official LightRAG chunking and embedding inputs without LLM calls."""
import argparse
from collections import Counter
import importlib.metadata
import inspect
from pathlib import Path
import sys
import os

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/evaluation')]
from workflow_io import read_json,atomic_json,file_hash,canonical_hash
from fair_runtime import light_rag_parameters


def prepare(inputs,protocol,model_manifest,tokenizer_cache,output):
    if output.exists():raise ValueError('Fresh output required')
    source=read_json(inputs/'manifest.json');settings=read_json(protocol);model=read_json(model_manifest)
    if source['dataset_manifest_sha256']!=settings['shared_inputs']['corpus_sha256']:raise ValueError('Wrong source corpus')
    if source['document_count']!=488 or len(source['documents'])!=488:raise ValueError('488 inputs required')
    parameters=light_rag_parameters(settings)
    if source['dense_conditions']!=settings['dense_conditions']:raise ValueError('Prepared dense conditions differ')
    model_path=Path(model['model_path'])
    if canonical_hash(model['model_files_sha256'])!=settings['dense_conditions']['model_files_sha256']:raise ValueError('Model pin differs')
    for name,digest in model['model_files_sha256'].items():
        if file_hash(model_path/name)!=digest:raise ValueError('Embedding tokenizer/model changed')
    os.environ['TIKTOKEN_CACHE_DIR']=str(tokenizer_cache.resolve())
    import tiktoken.load
    def offline(url):raise RuntimeError('Tokenizer downloads disabled')
    tiktoken.load.read_file=offline
    from lightrag.chunker import chunking_by_token_size
    from lightrag.utils import TiktokenTokenizer
    from tokenizers import Tokenizer
    tokenizer=TiktokenTokenizer('gpt-4o-mini')
    hf=Tokenizer.from_file(str(model_path/'tokenizer.json'));hf.no_truncation();hf.no_padding()
    maximum=read_json(model_path/'sentence_bert_config.json')['max_seq_length']
    unique={};papers=[];histogram=Counter();over=0;maximum_seen=0;all_chunks=0
    for row in source['documents']:
        path=(inputs/row['path']).resolve()
        if not path.is_relative_to(inputs.resolve()/'documents') or file_hash(path)!=row['sha256']:
            raise ValueError('LightRAG source changed or path unsafe')
        text=path.read_text(encoding='utf-8')
        chunks=chunking_by_token_size(tokenizer,text,chunk_token_size=parameters['chunk_token_size'],
                                     chunk_overlap_token_size=parameters['chunk_overlap_token_size'])
        count=0
        for chunk in chunks:
            content=chunk['content'];digest=canonical_hash(content)
            wordpieces=len(hf.encode(content,add_special_tokens=True).ids)
            maximum_seen=max(maximum_seen,wordpieces);count+=wordpieces>maximum
            histogram[min(wordpieces//64,20)*64]+=1
            unique.setdefault(digest,{'content_sha256':digest,'content':content,'o200k_tokens':len(tokenizer.encode(content)),
                                      'embedding_tokens_before_clipping':wordpieces,'source_papers':[]})
            unique[digest]['source_papers'].append(row['paper_id'])
        over+=count;all_chunks+=len(chunks)
        papers.append({'paper_id':row['paper_id'],'source_sha256':row['sha256'],'chunks':len(chunks),
                       'embedding_inputs_above_model_limit':count})
    output.mkdir(parents=True)
    atomic_json(output/'documents.json',papers)
    with (output/'chunks.jsonl').open('w',encoding='utf-8') as stream:
        import json
        for row in unique.values():stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    report={'state':'offline_chunking_plan_not_indexed','documents':488,'chunk_occurrences':all_chunks,
        'unique_chunk_contents':len(unique),'minimum_initial_extraction_calls_without_cache':len(unique),
        'additional_calls':'Gleaning disabled. Description summarization, method-specific query stages, failures, repairs and QA are not included.',
        'model_embedding_limit':maximum,'embedding_inputs_above_model_limit':over,'maximum_embedding_tokens_seen':maximum_seen,
        'embedding_token_histogram':dict(sorted(histogram.items())),'embedding_policy_required':'Use the same explicit MiniLM clipping policy as Vector and log truncation; do not silently rely on encoder truncation.',
        'chunk_parameters':parameters,'api_calls':0,'indexing_executed':False,'quality_scores_computed':False,
        'corpus_sha256':settings['shared_inputs']['corpus_sha256'],'input_manifest_sha256':file_hash(inputs/'manifest.json'),
        'protocol_sha256':file_hash(protocol),'chunk_file_sha256':file_hash(output/'chunks.jsonl'),
        'official_chunker_file_sha256':file_hash(Path(inspect.getfile(chunking_by_token_size))),
        'official_version':importlib.metadata.version('lightrag-hku'),'code_sha256':file_hash(Path(__file__)),
        'limits':'Budget assumes planned string-insert chunking, cold cache and one initial model extraction per unique chunk. It is a lower bound, not a guaranteed final API budget or completed SOTA comparison.'}
    atomic_json(output/'manifest.json',report)
    print({k:report[k] for k in ['documents','chunk_occurrences','unique_chunk_contents','embedding_inputs_above_model_limit','maximum_embedding_tokens_seen','api_calls']},flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('inputs','protocol','model-manifest','tokenizer-cache','output'):parser.add_argument('--'+name,type=Path,required=True)
    prepare(**vars(parser.parse_args()))
