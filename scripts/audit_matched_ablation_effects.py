import argparse
import csv
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/extraction'))
from workflow_io import atomic_json, canonical_hash, file_hash


def evidence_set(row):
    return {json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            for item in row['context']}


def source_set(row):
    sources = set()
    for item in row['context']:
        source = item.get('paper_id')
        if not isinstance(source, str) or not source:
            raise ValueError('Evidence lacks paper provenance')
        sources.add(Path(source).stem)
    return sources


def jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 1.0


def audit(rows, methods, question_ids):
    if 'kg' not in methods or len(set(methods)) != len(methods):
        raise ValueError('Invalid methods')
    grid = {}
    for row in rows:
        key = row['question_id'], row['method']
        if key in grid:
            raise ValueError('Duplicate grid cell')
        grid[key] = row
        text = json.dumps(row['context'], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        if text != row['context_json'] or canonical_hash(text) != row['context_sha256']:
            raise ValueError('Context integrity failure')
        if not isinstance(row['context_tokens'], int) or not 0 <= row['context_tokens'] <= 2000:
            raise ValueError('Token budget failure')
        source_set(row)
        if row['method'] == 'kg_no_expansion' and any('relation' in item for item in row['context']):
            raise ValueError('No-expansion relation leak')
    if set(grid) != {(q, m) for q in question_ids for m in methods}:
        raise ValueError('Incomplete or unexpected grid')
    pairs = []
    for q in question_ids:
        base = grid[q, 'kg']
        planned = ['query_plan' in grid[q, method] for method in methods]
        if any(planned) and not all(planned):
            raise ValueError('Missing query plan in paired methods')
        for method in methods:
            row = grid[q, method]
            if any(row[field] != base[field] for field in ('question', 'shared_query', 'paper_scope')):
                raise ValueError('Question/query/scope mismatch')
            if all(planned) and row['query_plan'] != base['query_plan']:
                raise ValueError('Query plan mismatch')
            if method == 'kg_verified' and row['context_json'] != base['context_json']:
                raise ValueError('Unpaired verifier context')
            if method == 'kg':
                continue
            a, b = evidence_set(base), evidence_set(row)
            sa, sb = source_set(base), source_set(row)
            pairs.append({'question_id': q, 'method': method,
                'ordered_context_changed': row['context_json'] != base['context_json'],
                'evidence_set_changed': a != b, 'source_set_changed': sa != sb,
                'evidence_jaccard': jaccard(a, b), 'source_jaccard': jaccard(sa, sb),
                'kg_items': len(base['context']), 'variant_items': len(row['context']),
                'kg_tokens': base['context_tokens'], 'variant_tokens': row['context_tokens'],
                'added_sources': sorted(sb - sa), 'removed_sources': sorted(sa - sb),
                'variant_empty': not row['context']})
    summaries = {}
    for method in methods:
        if method == 'kg':
            continue
        subset = [r for r in pairs if r['method'] == method]
        summaries[method] = {'questions': len(subset), **{
            field: sum(r[field] for r in subset) for field in
            ('ordered_context_changed', 'evidence_set_changed', 'source_set_changed', 'variant_empty')},
            'mean_source_jaccard': sum(r['source_jaccard'] for r in subset) / len(subset)}
    return pairs, summaries


def run(study, output):
    if output.exists():
        raise ValueError('Fresh output required')
    manifest = json.loads((study / 'manifest.json').read_text(encoding='utf-8'))
    source = study / 'contexts.jsonl'
    if file_hash(source) != manifest['contexts_sha256']:
        raise ValueError('Study manifest hash mismatch')
    rows = [json.loads(s) for s in source.read_text(encoding='utf-8').splitlines() if s]
    pairs, summaries = audit(rows, manifest['methods'], list(range(1, manifest['questions'] + 1)))
    output.mkdir(parents=True)
    with (output / 'question_pairs.jsonl').open('w', encoding='utf-8') as f:
        for row in pairs:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    with (output / 'method_summary.csv').open('w', encoding='utf-8-sig', newline='') as f:
        fields = ['method', *next(iter(summaries.values())).keys()]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows({'method': m, **r} for m, r in summaries.items())
    atomic_json(output / 'summary.json', {'records_audited': len(rows), 'comparisons': len(pairs),
        'methods_vs_kg': summaries, 'actual_api_calls': 0, 'quality_scores_computed': False,
        'limits': 'Development-context diagnostics only. Evidence overlap across passage and entity representations is not a quality metric. Source overlap is not source correctness. No QA superiority or statistical significance inferred.'})
    atomic_json(output / 'manifest.json', {'input_sha256': file_hash(source),
        'study_manifest_sha256': file_hash(study / 'manifest.json'), 'code_sha256': file_hash(Path(__file__))})
    shutil.copy2(Path(__file__), output / Path(__file__).name)
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    run(**vars(parser.parse_args()))
