"""Offline paired retrieval after source review of newly resolved alias edges."""
import argparse
from collections import defaultdict,deque,Counter
import json
import os
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src/extraction'),str(ROOT/'src/evaluation'),str(ROOT/'src/retrieval')]
from workflow_io import atomic_json,canonical_hash,file_hash
from verify_normalization_aliases import readlines,stats
from snapshot_benchmark import BM25Index
from hybrid_retrieval import build_query_plan,rerank_candidates
from context_budget import pack_v2,evidence_units
from paper_scope import PaperScope,ScopedIndex
from review_query_plan import build_plan


def expand(keys,index,adjacency,query,hops=2):
    queue=deque((keys[i],0,score) for i,score in index.search(query,24));visited={}
    while queue and len(visited)<240:
        node,hop,score=queue.popleft()
        if node in visited:continue
        visited[node]=(hop,score/(1+hop))
        if hop<hops:
            for neighbor in sorted(adjacency[node]):
                if neighbor not in visited:queue.append((neighbor,hop+1,score))
    return visited


def relation_tracks(original,source_checked,full_ablation=False,relation_policy='historical_combined'):
    if relation_policy not in {'historical_combined','fixed_source_checked'}:raise ValueError('Unknown relation policy')
    raw=original if relation_policy=='historical_combined' else source_checked
    tracks=[('raw',raw),('surface',raw),('pdf_alias_source_checked',source_checked)]
    if full_ablation:tracks += [('no_expansion',source_checked),('no_semantic',source_checked),('no_relation',source_checked)]
    return tracks


def select_scope(scoper,query,scope_policy):
    if scope_policy=='whole_corpus':return {'state':'whole_corpus','allowed_papers':None}
    if scope_policy!='title_scoped':raise ValueError('Unknown scope policy')
    return scoper.select(query) if scoper else {'state':'disabled','allowed_papers':None}


def run(study,queries,decisions,cache,output,reviewed_aliases=None,paper_corpus=None,review_planner=False,save_candidates=False,full_ablation=False,relation_policy='historical_combined',scope_policy='title_scoped'):
    if output.exists():raise ValueError('Fresh output required')
    select_scope(None,'',scope_policy)
    import tiktoken.load
    def offline(*args,**kwargs):raise RuntimeError('Tokenizer cache required; network disabled')
    tiktoken.load.read_file=offline;os.environ['TIKTOKEN_CACHE_DIR']=str(cache.resolve())
    import tiktoken
    encoding=tiktoken.get_encoding('o200k_base');encode=lambda s:encoding.encode(s,disallowed_special=())
    entities=readlines(study/'entities.jsonl');original=readlines(study/'relations.jsonl')
    reviewed=read_json_aliases(reviewed_aliases) if reviewed_aliases else []
    reviewed_by_id={r['occurrence_id']:r for r in reviewed}
    for record in reviewed:
        entity=next((e for e in entities if e['occurrence_id']==record['occurrence_id']),None)
        if not entity or entity['paper']!=record['paper'] or entity['type']!=record['type']:raise ValueError('Alias scope mismatch')
    alias=study/'pdf_alias_track';proposed=readlines(alias/'relations_alias_track.jsonl')
    if len(original)!=len(proposed) or any((a['paper'],a['index'])!=(b['paper'],b['index']) for a,b in zip(original,proposed)):
        raise ValueError('Original and proposed relation inventories differ')
    reviews=json.loads(decisions.read_text(encoding='utf-8'));reviewmap={(r['paper'],r['index']):r for r in reviews}
    newly_resolved={(r['paper'],r['index']) for a,r in zip(original,proposed) if a['state']!='resolved' and r['state']=='resolved'}
    if set(reviewmap)!=newly_resolved or len(reviews)!=len(newly_resolved):raise ValueError('Review must cover exactly all 11 new edges')
    final=[]
    for a,b in zip(original,proposed):
        if (b['paper'],b['index']) in reviewmap:
            review=reviewmap[b['paper'],b['index']]
            if review['decision'] not in {'include_in_experimental_track','exclude','pending'}:raise ValueError('Unknown review decision')
            final.append(b if review['decision']=='include_in_experimental_track' else a)
        else:final.append(a)
    maps=json.loads((alias/'identity_maps.json').read_text(encoding='utf-8'))
    qrows=readlines(queries);questions={}
    for r in qrows:
        value=(r['question'],r['shared_query'])
        if r['question_id'] in questions and questions[r['question_id']]!=value:raise ValueError('Query differs across methods')
        questions[r['question_id']]=value
    if set(questions)!=set(range(1,46)):raise ValueError('45 questions required')
    title_files=sorted(paper_corpus.glob('*.json')) if paper_corpus else []
    titles={p.name:json.loads(p.read_text(encoding='utf-8-sig')).get('title','') for p in title_files}
    scoper=PaperScope(titles) if titles else None
    output.mkdir(parents=True);results=[];graphstats={};index_timings={}
    tracks=relation_tracks(original,final,full_ablation,relation_policy)
    for track,relations in tracks:
        use_alias=track not in {'raw','surface'}
        hops=0 if track=='no_expansion' else 2
        multipliers={'semantic':0} if track=='no_semantic' else {'relation':0} if track=='no_relation' else None
        mapping=maps['pdf_declared_alias' if use_alias else track]
        groups=defaultdict(list)
        for entity in entities:groups[mapping[entity['occurrence_id']]].append(entity)
        adjacency={key:set() for key in groups};incident=defaultdict(list);edges=[];typed_neighbors=defaultdict(set)
        for relation in relations:
            if relation['state']!='resolved':continue
            a,b=[mapping[e['ids'][0]] for e in relation['endpoints']]
            adjacency[a].add(b);adjacency[b].add(a)
            relation_type=relation['source_relation']['type']
            typed_neighbors[a].add((b,relation_type));typed_neighbors[b].add((a,relation_type))
            evidence={'source_file':relation['paper'],'paper_id':relation['paper'],'relation':relation['source_relation']}
            for key in {a,b}:incident[key].append(evidence)
            edges.append({'source':a,'target':b,'type':relation['source_relation']['type'],'paper':relation['paper'],'original_relation_index':relation['index'],
                          'review':reviewmap.get((relation['paper'],relation['index'])),'production_approved':False})
        keys=sorted(groups)
        def index_text(key):
            text=' '.join(dict.fromkeys(o['name']+' '+str(o['source_entity'].get('description','')) for o in groups[key]))
            if titles:text+=' '+' '.join(dict.fromkeys(titles.get(o['paper'],'') for o in groups[key]))
            if use_alias:
                aliases=[name for o in groups[key] for name in reviewed_by_id.get(o['occurrence_id'],{}).get('aliases',[])]
                extra=[name for name in dict.fromkeys(aliases) if name.casefold() not in text.casefold()]
                text+=' '+' '.join(extra)
            return text
        index_started=time.perf_counter()
        index=BM25Index([index_text(key) for key in keys])
        index_timings[track]=time.perf_counter()-index_started
        for qid,(question,query) in sorted(questions.items()):
            query_started=time.perf_counter()
            scope=select_scope(scoper,query,scope_policy)
            search_index=ScopedIndex(index,keys,groups,scope['allowed_papers']) if scope['allowed_papers'] is not None else index
            scope_finished=time.perf_counter()
            found=expand(keys,search_index,adjacency,query,hops=hops);candidates=[]
            if scope['allowed_papers'] is not None and any(o['paper'] not in scope['allowed_papers'] for key in found for o in groups[key]):raise ValueError('Paper scope leaked across graph expansion')
            for key,(hop,score) in found.items():
                group=groups[key];first=group[0]
                candidates.append({'entity_type':first['type'],'entity_name':first['name'],
                    'entity_desc':' '.join(dict.fromkeys(str(o['source_entity'].get('description','')) for o in group)),
                    'source_papers':sorted({titles.get(o['paper'],o['paper']) for o in group}),'source_count':len({o['paper'] for o in group}),
                    'hop_distance':hop,'degree':len(adjacency[key]) if hops else 0,'retrieval_score':score,
                    'connections':[{'relation':kind,'related_name':groups[n][0]['name'],'related_type':groups[n][0]['type'],'related_desc':''} for n,kind in sorted(typed_neighbors[key])[:24]] if hops else [],
                    'evidence_occurrences':[{'source_file':o['paper'],'paper_id':o['paper'],'entity':o['source_entity']} for o in group],
                    'relation_occurrences':incident[key] if hops else []})
            candidates_finished=time.perf_counter()
            plan=build_plan(query) if review_planner else build_query_plan(query,{'keywords':[query]})
            if save_candidates and track=='pdf_alias_source_checked':
                saved=output/'candidate_snapshot';saved.mkdir(exist_ok=True)
                atomic_json(saved/f'q{qid}.json',{'question_id':qid,'question':question,'shared_query':query,'plan':plan,'candidates':candidates})
            ranking_audit={} if track=='raw' else None
            ranked=rerank_candidates(query,plan,candidates,max_context=8,audit=ranking_audit,signal_multipliers=multipliers)
            if track=='raw' and not ranked:
                audit_folder=output/'empty_context_audits';audit_folder.mkdir(exist_ok=True)
                atomic_json(audit_folder/f'q{qid}.json',{'question':question,'shared_query':query,'paper_scope':scope,'query_plan':plan,'ranking_audit':ranking_audit})
            ranking_finished=time.perf_counter()
            context,text,count,audit=pack_v2(evidence_units(ranked),encode)
            packing_finished=time.perf_counter()
            results.append({'question_id':qid,'question':question,'shared_query':query,'track':track,'context':context,
                'context_json':text,'context_sha256':canonical_hash(text),'context_tokens':count,'candidate_nodes':sorted(found),
                'packing_audit':audit,'paper_scope':scope,'query_plan':plan,'quality_score':None,'generation_status':'not_executed',
                'timing':{'source_selection_seconds':scope_finished-query_started,
                    'search_expansion_candidates_seconds':candidates_finished-scope_finished,
                    'planning_ranking_seconds':ranking_finished-candidates_finished,
                    'packing_seconds':packing_finished-ranking_finished,
                    'retrieval_wall_seconds':packing_finished-query_started,
                    'scope':'In-process frozen-query retrieval; excludes index setup, generation, verifier and API. Optional diagnostic writes inside ranking interval.'}})
        graphstats[track]=stats(mapping,relations)
        atomic_json(output/(track+'_graph.json'),{'nodes':[{'id':key,'source_occurrences':group} for key,group in sorted(groups.items())],
            'edges':edges,'status':'local_experimental_graph_not_production_not_gold'})
    with (output/'paired_contexts.jsonl').open('w',encoding='utf-8') as f:
        for r in results:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    lookup={(r['question_id'],r['track']):r for r in results}
    changes=[]
    for q in range(1,46):
        a=lookup[q,'raw'];b=lookup[q,'pdf_alias_source_checked']
        changes.append({'question_id':q,'candidate_set_changed':a['candidate_nodes']!=b['candidate_nodes'],
                        'context_changed':a['context_json']!=b['context_json'],'raw_tokens':a['context_tokens'],'alias_tokens':b['context_tokens']})
    atomic_json(output/'changes_by_question.json',changes)
    summary={'questions':45,'tracks':len(tracks),'records':len(results),'structural_comparison':graphstats,'review_decisions':dict(Counter(r['decision'] for r in reviews)),
        'changed_candidate_sets':sum(r['candidate_set_changed'] for r in changes),'changed_contexts':sum(r['context_changed'] for r in changes),
        'empty_contexts_by_track':{track:sum(not r['context'] for r in results if r['track']==track) for track in graphstats},
        'max_tokens':max(r['context_tokens'] for r in results),'actual_api_calls':0,'quality_scores_computed':False,
        'scope_policy':scope_policy,
        'index_build_seconds_by_track':index_timings,
        'limits':'New paper-local entity-edge diagnostic; no Paper/MENTIONS or production Neo4j. Not directly comparable to older global graph context counts. Context differences are not relevance/recall/QA improvements. Existing base edges were not all semantically re-reviewed.'}
    atomic_json(output/'summary.json',summary)
    atomic_json(output/'manifest.json',{'code_sha256':file_hash(Path(__file__)),'input_hashes':{str(p.resolve()):file_hash(p) for p in [study/'entities.jsonl',study/'relations.jsonl',alias/'relations_alias_track.jsonl',alias/'identity_maps.json',queries,decisions]},
        'relation_policy':relation_policy,
        'relation_occurrences_sha256_by_track':{track:canonical_hash(relations) for track,relations in tracks},
        'normalization_interpretation':'Identity/index-alias intervention with source-checked relation occurrences held fixed' if relation_policy=='fixed_source_checked' else 'Combined normalization and alias endpoint-resolution intervention; not identity-only ablation',
        'retrieval':'Fixed BM25 entity descriptions, 24 anchors, 240 candidates, 2 hops, same reranker, top8, evidence_units+pack_v2, 2000 o200k tokens; deterministic ordering',
        'reviewed_aliases_sha256':file_hash(reviewed_aliases) if reviewed_aliases else None,
        'paper_title_inputs_sha256':{p.name:file_hash(p) for p in title_files},
        'paper_scope_code_sha256':file_hash(ROOT/'src/retrieval/paper_scope.py'),
        'review_planner':review_planner,'review_planner_code_sha256':file_hash(ROOT/'src/retrieval/review_query_plan.py'),
        'full_ablation':full_ablation,
        'scope_policy':scope_policy,
        'paper_scope_policy':('Whole corpus searched for every question and every track; titles remain searchable metadata but never restrict source candidates.'
                              if scope_policy=='whole_corpus' else
                              'Optional source title appended to all node index texts. Title anchors df<=3: require pair/code or two informative anchors in same paper; union up to 8 papers; same shared query/all tracks; no answer labels; experimental not validated quality gain'),
        'alias_index_policy':'Paper-scoped source-reviewed alternative names appended only when absent from existing index text; never alter source evidence.',
        'dependency_hashes':{p.name:file_hash(p) for p in [ROOT/'src/evaluation/context_budget.py',ROOT/'src/evaluation/snapshot_benchmark.py',ROOT/'src/retrieval/hybrid_retrieval.py']}})
    print(json.dumps(summary,ensure_ascii=False))


def read_json_aliases(path):
    records=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(records,list) or len({r['occurrence_id'] for r in records})!=len(records):raise ValueError('Unique scoped aliases required')
    for record in records:
        if record.get('decision')!='include_in_experimental_track' or not record.get('evidence') or not isinstance(record.get('aliases'),list):raise ValueError('Reviewed source evidence required')
    return records


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('study','queries','decisions','cache','output'):p.add_argument('--'+flag,type=Path,required=True)
    p.add_argument('--reviewed-aliases',type=Path)
    p.add_argument('--paper-corpus',type=Path)
    p.add_argument('--review-planner',action='store_true')
    p.add_argument('--save-candidates',action='store_true')
    p.add_argument('--full-ablation',action='store_true')
    p.add_argument('--relation-policy',choices=['historical_combined','fixed_source_checked'],default='historical_combined')
    p.add_argument('--scope-policy',choices=['title_scoped','whole_corpus'],default='title_scoped')
    run(**vars(p.parse_args()))
