"""Exploratory paired retrieval timing for the supplied-KG comparison."""
import argparse
import math
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src/extraction'), str(ROOT/'src/evaluation')]
from workflow_io import atomic_json, read_json, loads, file_hash
from revision_statistics import paired_inference, percentile

METHODS = ('bm25', 'vector', 'lightrag_shared_kg')


def analyze(rows, draws=10000):
    grid = {}
    for row in rows:
        key = (row['method'], row['question_id'], row['repeat'])
        value = row['retrieval_wall_seconds']
        if key in grid or type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('Duplicate or invalid timing')
        if type(key[1]) is not int or type(key[2]) is not int:
            raise ValueError('Integer question and repeat required')
        grid[key] = row
    if set(grid) != {(m, q, r) for m in METHODS for q in range(1, 46) for r in range(1, 6)}:
        raise ValueError('Complete 45-question, five-repeat grid required')
    means = {}; summary = []
    for method in METHODS:
        means[method] = []
        within = []
        for q in range(1, 46):
            group = [grid[method, q, r] for r in range(1, 6)]
            if len({r['context_sha256'] for r in group}) != 1:
                raise ValueError('Context changed across repeats')
            values = [r['retrieval_wall_seconds'] for r in group]
            means[method].append(statistics.mean(values)); within.append(statistics.stdev(values))
        rng = random.Random(20261123)
        samples = [statistics.mean(rng.choices(means[method], k=45)) for _ in range(draws)]
        summary.append({'method': method, 'mean_seconds': statistics.mean(means[method]),
            'sd_between_question_means': statistics.stdev(means[method]),
            'mean_within_question_sd': statistics.mean(within),
            'bootstrap_95_ci': [percentile(samples, .025), percentile(samples, .975)]})
    tests = []
    for left, right in [('vector','bm25'), ('lightrag_shared_kg','bm25'), ('lightrag_shared_kg','vector')]:
        tests.append({'left': left, 'right': right, **paired_inference(
            [a-b for a,b in zip(means[left], means[right])], seed=20261123, draws=draws)})
    previous = 0
    for rank, test in enumerate(sorted(tests, key=lambda t:t['paired_sign_flip_p'])):
        previous = max(previous, min(1, (len(tests)-rank)*test['paired_sign_flip_p']))
        test['holm_adjusted_p'] = previous
    return {'records': len(rows), 'questions': 45, 'repeats': 5, 'summary': summary,
        'paired_tests': tests, 'unit': 'seconds; left minus right; positive means left slower',
        'inference_unit': 'question; five repeats averaged first', 'resampling_draws': draws,
        'scope': 'Exploratory local retrieval on precomputed shared queries; not QA or end-to-end latency',
        'limits': 'Separate sequential method sessions, not interleaved randomized timing. Shared CPU/model/backend but different passage/fact units and native algorithms. LightRAG supplied KG and explicit query keywords only. Excludes indexing, extraction, translation, answer synthesis and verification.',
        'quality_scores_computed': False}


def run(study, output):
    if output.exists(): raise ValueError('Fresh output required')
    rows = []; inputs = {}
    for directory in ('baselines', 'lightrag_shared_kg'):
        root = study/directory; manifest = read_json(root/'manifest.json')
        if file_hash(root/'contexts.jsonl') != manifest['contexts_sha256']:
            raise ValueError('Changed context artifact')
        if file_hash(root/'runtime.json') != manifest['runtime_sha256']:
            raise ValueError('Changed runtime artifact')
        timings = read_json(root/'timings.json')
        if 'timings_sha256' in manifest and file_hash(root/'timings.json') != manifest['timings_sha256']:
            raise ValueError('Changed timing artifact')
        contexts = {(r['method'],r['question_id']):r for r in
            [loads(s) for s in (root/'contexts.jsonl').read_text(encoding='utf-8').split('\n') if s]}
        for row in timings:
            if row['context_sha256'] != contexts[row['method'],row['question_id']]['context_sha256']:
                raise ValueError('Timing/context mismatch')
        rows.extend(timings)
        inputs[directory] = {name:file_hash(root/name) for name in
            ('timings.json','contexts.jsonl','manifest.json','runtime.json')}
    result = analyze(rows)
    result['provenance'] = {'inputs':inputs,'code_sha256':file_hash(Path(__file__)),
        'helper_sha256':file_hash(ROOT/'src/evaluation/revision_statistics.py'),
        'timing_binding_limit':'LightRAG original manifest omitted timing hash; timing frozen now, not retroactively bound at measurement time.'}
    atomic_json(output,result)
    print([(s['method'],round(s['mean_seconds']*1000,3)) for s in result['summary']])


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.study,a.output)
