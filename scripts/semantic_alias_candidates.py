import argparse
from collections import defaultdict,Counter
import csv
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'scripts')]
from workflow_io import read_json,atomic_json,file_hash,canonical_hash
from normalization_review_study import surface


def candidate_pairs(records,vectors,threshold=.8,top_k=3):
    import numpy as np
    matrix=np.asarray(vectors)
    if matrix.ndim!=2 or len(matrix)!=len(records) or not np.isfinite(matrix).all():raise ValueError('Invalid embeddings')
    if not np.allclose(np.linalg.norm(matrix,axis=1),1,atol=1e-4):raise ValueError('Unit-normalized vectors required')
    if not 0<=threshold<=1 or type(top_k) is not int or top_k<1:raise ValueError('Invalid candidate policy')
    groups=defaultdict(list)
    for i,r in enumerate(records):groups[r['type']].append(i)
    found={}
    for indices in groups.values():
        ids=np.array(indices);subset=matrix[ids]
        for start in range(0,len(ids),256):
            scores=subset[start:start+256]@subset.T
            for offset,row in enumerate(scores):
                i=int(ids[start+offset]);selected=0
                for position in np.lexsort((ids,-row)):
                    j=int(ids[position]);score=float(row[position])
                    if score<threshold:break
                    if i==j or surface(records[i]['name'])==surface(records[j]['name']):continue
                    pair=tuple(sorted((i,j)));found[pair]=max(score,found.get(pair,-1));selected+=1
                    if selected>=top_k:break
    return [(i,j,score) for (i,j),score in sorted(found.items(),key=lambda item:(-item[1],item[0]))]


def run(entities,vector_manifest,output):
    if output.exists():raise ValueError('Fresh output required')
    model_info=read_json(vector_manifest);model_path=Path(model_info['model_path'])
    if any(file_hash(model_path/name)!=digest for name,digest in model_info['model_files_sha256'].items()):raise ValueError('Cached model changed')
    rows=[json.loads(s) for s in entities.read_text(encoding='utf-8').split('\n') if s]
    grouped=defaultdict(list)
    for row in rows:
        if row['type'] in {'Method','Dataset','Concept'}:grouped[row['type'],row['name']].append(row)
    records=[{'type':kind,'name':name,'occurrences':occurrences} for (kind,name),occurrences in sorted(grouped.items())]
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(4)
    model=SentenceTransformer(str(model_path),device='cpu',local_files_only=True,trust_remote_code=False)
    lengths=[len(model.tokenizer(r['name'],add_special_tokens=True)['input_ids']) for r in records]
    print('Encoding',len(records),'distinct typed names from cached model',flush=True)
    matrix=model.encode([r['name'] for r in records],batch_size=64,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)
    pairs=candidate_pairs(records,matrix)
    output.mkdir(parents=True);np.save(output/'name_embeddings.npy',matrix,allow_pickle=False)
    proposals=[]
    for i,j,score in pairs:
        a,b=records[i],records[j];pa={r['paper'] for r in a['occurrences']};pb={r['paper'] for r in b['occurrences']}
        numbers_a=re.findall(r'\d+(?:\.\d+)?',a['name']);numbers_b=re.findall(r'\d+(?:\.\d+)?',b['name'])
        proposals.append({'candidate_id':canonical_hash([a['type'],a['name'],b['name']]),'type':a['type'],'name_a':a['name'],'name_b':b['name'],
            'cosine':score,'shared_papers':sorted(pa&pb),'occurrences_a':a['occurrences'],'occurrences_b':b['occurrences'],
            'qualifier_warning':'numeric_or_model_variant_difference' if numbers_a!=numbers_b else None,
            'decision':'pending_source_review','auto_merge':False,'pdf_identity_verified':False,'independent_gold':False})
    with (output/'candidates.jsonl').open('w',encoding='utf-8') as f:
        for row in proposals:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    atomic_json(output/'name_index.json',records)
    with (output/'review_queue.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['candidate_id','type','name_a','name_b','cosine','shared_papers','qualifier_warning','decision','source_pdf','page_pdf','quote','reviewer','notes'])
        for r in proposals:w.writerow([r['candidate_id'],r['type'],r['name_a'],r['name_b'],r['cosine'],';'.join(r['shared_papers']),r['qualifier_warning'],'pending_source_review','','','','',''])
    summary={'typed_names':len(records),'candidate_pairs':len(proposals),'pairs_by_type':dict(Counter(p['type'] for p in proposals)),
        'same_paper_pairs':sum(bool(r['shared_papers']) for r in proposals),'numeric_qualifier_warnings':sum(bool(r['qualifier_warning']) for r in proposals),
        'truncated_name_inputs':sum(n>model.max_seq_length for n in lengths),'actual_api_calls':0,'graph_merges_applied':0,'quality_scores_computed':False,
        'limits':'Candidate discovery only, not number of synonyms or recall. General English MiniLM can confuse related methods, model variants and conditions. No Author/Institution/Metric/Domain merges. Gold annotators must not see predictions before independent annotation.'}
    atomic_json(output/'summary.json',summary)
    atomic_json(output/'manifest.json',{'entities_sha256':file_hash(entities),'vector_manifest_sha256':file_hash(vector_manifest),'code_sha256':file_hash(Path(__file__)),
        'model_files_sha256':model_info['model_files_sha256'],'device':'cpu','threads':4,'embedding_shape':list(matrix.shape),
        'policy':'Same-type non-identical names, cosine>=0.8, top3 per name, stable ties, candidates only, no labels/QA questions used',
        'packages':{p:importlib.metadata.version(p) for p in ['numpy','torch','sentence-transformers','transformers']}})
    if any(file_hash(model_path/name)!=digest for name,digest in model_info['model_files_sha256'].items()):raise ValueError('Model changed during run')
    print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for flag in ('entities','vector-manifest','output'):p.add_argument('--'+flag,type=Path,required=True)
    run(**vars(p.parse_args()))
