"""Prepare a provenance-preserving experimental Neo4j import, without connecting."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src/extraction'), str(ROOT / 'scripts')]
from workflow_io import atomic_json, file_hash, read_json
from prepare_review_dataset import verify


def build_records(graph, papers):
    nodes, mentions, edges = [], [], []
    identities = set()
    for node in graph['nodes']:
        key = node['id']
        if not isinstance(key, str) or not key or key in identities:
            raise ValueError('Missing or duplicate node identity')
        identities.add(key)
        occurrences = node['source_occurrences']
        if not occurrences:
            raise ValueError('Node without provenance')
        types = {o['type'] for o in occurrences}
        if len(types) != 1 or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', next(iter(types))):
            raise ValueError('Ambiguous or invalid entity type')
        names = list(dict.fromkeys(o['name'] for o in occurrences))
        descriptions = list(dict.fromkeys(o['source_entity'].get('description', '') for o in occurrences))
        nodes.append({'key': key, 'label': next(iter(types)), 'name': names[0],
                      'aliases': names, 'description': '\n'.join(x for x in descriptions if x),
                      'provenance_json': json.dumps(occurrences, ensure_ascii=False),
                      'production_approved': False})
        for paper in sorted({o['paper'] for o in occurrences}):
            if paper not in papers:
                raise ValueError('Unknown provenance paper')
            mentions.append({'paper': paper, 'entity': key})
    membership = {(r['paper'], r['entity']) for r in mentions}
    for index, edge in enumerate(graph['edges']):
        if edge['source'] not in identities or edge['target'] not in identities:
            raise ValueError('Dangling relation endpoint')
        if any((edge['paper'], edge[k]) not in membership for k in ('source', 'target')):
            raise ValueError('Relation crosses paper provenance')
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', edge['type']):
            raise ValueError('Invalid relation type')
        edges.append({**edge, 'key': f'relation:{index}', 'production_approved': False})
    return {'papers': list(papers.values()), 'entities': nodes, 'mentions': mentions, 'relations': edges}


def prepare(dataset, graph_path, output):
    if output.exists():
        raise ValueError('Fresh output directory required')
    verify(dataset)
    papers = {}
    for path in sorted((dataset / 'corpus').glob('*.json')):
        row = read_json(path)
        papers[path.name] = {'key': path.name, 'filename': row.get('filename', path.name),
                             'title': row.get('title', ''), 'corpus_sha256': file_hash(path),
                             'production_approved': False}
    records = build_records(read_json(graph_path), papers)
    output.mkdir(parents=True)
    atomic_json(output / 'records.json', records)
    manifest = {'status': 'experimental_not_independently_validated',
                'target_database': 'graphrag-review-482', 'live_database_allowed': False,
                'frozen_manifest_sha256': file_hash(dataset / 'manifest.json'),
                'graph_sha256': file_hash(graph_path), 'code_sha256': file_hash(Path(__file__)),
                'records_sha256': file_hash(output / 'records.json'),
                'counts': {k: len(v) for k, v in records.items()},
                'database_writes_performed': False,
                'limits': 'MENTIONS is a provenance link. Descriptions are historical extraction, not expert-verified evidence. Native retrieval may differ from snapshot retrieval.'}
    atomic_json(output / 'manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--graph', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.dataset, args.graph, args.output), indent=2))
