"""Exercise native Neo4j retrieval without generation or quality scoring."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src/retrieval'), str(ROOT / 'src/extraction')]
from import_neo4j_snapshot import credentials
from prepare_review_dataset import read_questions
from workflow_io import atomic_json, file_hash
from hybrid_retrieval import build_query_plan, retrieve_candidates, rerank_candidates
from paper_scope import PaperScope


def run(credential_file, questions, output, matched=None, corpus=None, count=3, graph=None):
    from neo4j import GraphDatabase
    if output.exists():
        raise ValueError('Fresh output required')
    os.environ['NEO4J_DATABASE'] = 'graphrag-review-482'
    results = []
    shared = {}
    if matched:
        for line in matched.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            qid = row['question_id']
            value = row['shared_query']
            if qid in shared and shared[qid] != value:
                raise ValueError('Shared query differs across methods')
            shared[qid] = value
        if set(shared) != set(range(1, 46)) or corpus is None:
            raise ValueError('Need 45 shared queries and frozen corpus')
    names = [o['name'] for n in json.loads(graph.read_text(encoding='utf-8'))['nodes'] for o in n['source_occurrences']] if graph else []
    scoper = PaperScope({p.name:json.loads(p.read_text(encoding='utf-8-sig')).get('title','') for p in corpus.glob('*.json')}, entity_names=names) if corpus else None
    with GraphDatabase.driver('bolt://127.0.0.1:7687', auth=credentials(credential_file), max_transaction_retry_time=0) as driver:
        for index, row in enumerate(read_questions(questions)[:count], 1):
            start = time.perf_counter()
            query = shared.get(index, row['question'])
            plan = build_query_plan(row['question'])
            paper_scope = scoper.select(query, named_entities=plan.get('entities', [])) if scoper else {'allowed_papers':None}
            if shared:
                plan['search_terms'] = [query]
            candidates, diagnostics = retrieve_candidates(driver, row['question'], plan, allowed_papers=paper_scope['allowed_papers'])
            if paper_scope['allowed_papers'] is not None:
                allowed = set(paper_scope['allowed_papers'])
                for candidate in candidates:
                    if candidate['entity_type'] != 'Paper' and (not candidate['source_paper_keys'] or not set(candidate['source_paper_keys']) <= allowed):
                        raise ValueError('Candidate provenance outside paper scope')
            audit = {}
            selected = rerank_candidates(row['question'], plan, candidates, audit=audit)
            results.append({'question_id':index, 'question':row['question'], 'plan':plan,
                            'shared_query':query, 'paper_scope':paper_scope,
                            'diagnostics':diagnostics, 'selected':selected, 'ranking_audit':audit,
                            'retrieval_wall_seconds':time.perf_counter()-start,
                            'candidate_types':sorted({r['entity_type'] for r in candidates})})
    report = {'database':'graphrag-review-482', 'generation_api_calls':0, 'quality_scores':None,
              'scope':'native retrieval diagnostic; not benchmark latency or answer-quality scoring',
              'matched_contexts_sha256':file_hash(matched) if matched else None,
              'questions_sha256':file_hash(questions),
              'retrieval_code_sha256':file_hash(ROOT / 'src/retrieval/hybrid_retrieval.py'), 'results':results}
    report['paper_scope_code_sha256'] = file_hash(ROOT / 'src/retrieval/paper_scope.py')
    report['scope_entity_graph_sha256'] = file_hash(graph) if graph else None
    atomic_json(output, report)
    print(json.dumps([{'question_id':r['question_id'], 'candidates':r['diagnostics']['candidates'],
                       'selected':len(r['selected']), 'types':r['candidate_types']} for r in results]))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credential-file', type=Path, required=True)
    parser.add_argument('--questions', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--matched', type=Path)
    parser.add_argument('--corpus', type=Path)
    parser.add_argument('--count', type=int, default=3, choices=range(1,46))
    parser.add_argument('--graph', type=Path)
    args = parser.parse_args()
    run(args.credential_file, args.questions, args.output, args.matched, args.corpus, args.count, args.graph)
