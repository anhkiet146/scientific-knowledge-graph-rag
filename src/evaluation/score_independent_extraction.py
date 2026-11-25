"""Strict paper-scoped scoring; refuse pending or source-mismatched gold.

Annotation metadata is an attestation, not proof that humans worked independently.
This module never generates reference labels or performs fuzzy/LLM matching.
"""
import argparse
import collections
import json
import random
import unicodedata
import sys
from pathlib import Path

PROTOCOL = json.loads((Path(__file__).resolve().parents[2] / 'configs/strict_protocol_v3_1.json').read_text(encoding='utf-8'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'extraction'))
from strict_validation import VALUE


def identity(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value)).split())


def records(document):
    payload = document.get('extraction_result', document)
    entities = collections.Counter()
    types = collections.defaultdict(set)
    identifiers = collections.defaultdict(set)
    for entity in payload['entities']:
        if not isinstance(entity,dict) or not isinstance(entity.get('id'),str) or not isinstance(entity.get('type'),str):
            raise ValueError('Invalid entity record')
        name, typ = identity(entity['id']), entity['type']
        if not name or typ not in PROTOCOL['entity_types']:
            raise ValueError('Empty identifier or unknown entity type')
        display=entity.get('name',entity['id'])
        if not isinstance(display,str) or not display.strip():raise ValueError('Invalid source name')
        semantic_name=identity(display)
        if typ=='Metric':
            measurement=entity.get('measurement')
            fields=PROTOCOL['metric_identity_fields']
            if not isinstance(measurement,dict) or set(measurement)!=set(fields) or any(not isinstance(measurement[f],str) for f in fields):
                raise ValueError('Structured Metric fields required under v3 scoring')
            if (not VALUE.fullmatch(identity(measurement['value'])) or not measurement['endpoint'].strip()
                or not measurement['object'].strip() or measurement['source_report'] not in {'abstract','prose','table'}):
                raise ValueError('Invalid structured Metric identity')
            semantic_name=json.dumps([identity(measurement[f]) for f in fields],ensure_ascii=False)
        entities[(semantic_name, typ)] += 1
        types[name].add(typ)
        identifiers[name].add(semantic_name)
    relations = collections.Counter()
    for relation in payload['relations']:
        src, tgt = identity(relation['source']), identity(relation['target'])
        if len(types[src]) != 1 or len(types[tgt]) != 1 or len(identifiers[src])!=1 or len(identifiers[tgt])!=1:
            raise ValueError('Missing or ambiguous typed relation endpoint')
        signature = [next(iter(types[src])), next(iter(types[tgt]))]
        if PROTOCOL['relation_signatures'].get(relation['type']) != signature:
            raise ValueError('Unknown relation or invalid type signature')
        relations[(next(iter(identifiers[src])), next(iter(types[src])), relation['type'],
                   next(iter(identifiers[tgt])), next(iter(types[tgt])))] += 1
    return entities, relations


def counts(predicted, gold):
    tp = sum((predicted & gold).values())
    return {'tp': tp, 'fp': sum(predicted.values()) - tp,
            'fn': sum(gold.values()) - tp}


def measures(count):
    tp, fp, fn = (count[k] for k in ('tp', 'fp', 'fn'))
    return {**count, 'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None,
            'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None}


def aggregate(papers, kind):
    result = {key: sum(p[kind][key] for p in papers) for key in ('tp', 'fp', 'fn')}
    return measures(result)


def score(predictions, references, draws=2000, seed=20261112):
    if not references or draws < 1:
        raise ValueError('Nonempty independently adjudicated references and positive draws required')
    gold_by_id = {}
    for gold in references:
        name = Path(gold['filename']).stem
        annotators = gold.get('annotators', [])
        if (gold.get('annotation_status') != 'adjudicated' or len(set(annotators)) < 2
                or not gold.get('adjudication_log') or not gold.get('source_sha256')):
            raise ValueError('Pending/incomplete independent annotation metadata: ' + name)
        if name in gold_by_id:
            raise ValueError('Duplicate reference paper: ' + name)
        gold_by_id[name] = gold
    predicted_by_id = {}
    for document in predictions:
        name = Path(document['filename']).stem
        if name in predicted_by_id or name not in gold_by_id:
            raise ValueError('Duplicate or out-of-sample prediction: ' + name)
        if document.get('source_sha256') != gold_by_id[name]['source_sha256']:
            raise ValueError('Source checksum mismatch: ' + name)
        predicted_by_id[name] = document
    papers = []
    typed = {'entities': collections.defaultdict(lambda: dict(tp=0, fp=0, fn=0)),
             'relations': collections.defaultdict(lambda: dict(tp=0, fp=0, fn=0))}
    for name, gold in sorted(gold_by_id.items()):
        reference = records(gold)
        prediction = records(predicted_by_id[name]) if name in predicted_by_id else (collections.Counter(), collections.Counter())
        row = {'paper_id': name, 'missing_prediction': name not in predicted_by_id}
        for index, kind in enumerate(('entities', 'relations')):
            pred, ref = prediction[index], reference[index]
            if any(value > 1 for value in ref.values()):
                raise ValueError('Duplicate gold record: ' + name)
            row[kind] = counts(pred, ref)
            label_index = 1 if kind == 'entities' else 2
            for label in {item[label_index] for item in set(pred) | set(ref)}:
                c = counts(collections.Counter({k: v for k, v in pred.items() if k[label_index] == label}),
                           collections.Counter({k: v for k, v in ref.items() if k[label_index] == label}))
                for key in c:
                    typed[kind][label][key] += c[key]
        papers.append(row)
    rng = random.Random(seed)
    result = {'unit': 'paper', 'matching': PROTOCOL['matching'], 'protocol_id': PROTOCOL['protocol_id'],
              'n_papers': len(papers), 'missing_predictions': sum(p['missing_prediction'] for p in papers),
              'annotation_independence': 'metadata attested; must be independently audited', 'per_paper': papers}
    for kind in ('entities', 'relations'):
        micro = aggregate(papers, kind)
        samples = []
        for _ in range(draws):
            value = aggregate(rng.choices(papers, k=len(papers)), kind)['f1']
            if value is not None:
                samples.append(value)
        samples.sort()
        def percentile(q):
            position = (len(samples) - 1) * q
            low = int(position)
            high = min(low + 1, len(samples) - 1)
            return samples[low] + (samples[high] - samples[low]) * (position - low)
        by_type = {label: measures(c) for label, c in sorted(typed[kind].items())}
        macro = {}
        for metric in ('precision', 'recall', 'f1'):
            values = [v[metric] for v in by_type.values() if v[metric] is not None]
            macro[metric] = sum(values) / len(values) if values else None
        result[kind] = {'micro': micro, 'per_type': by_type, 'macro': macro,
                        'bootstrap_micro_f1_95_ci': [percentile(.025), percentile(.975)] if samples else None,
                        'bootstrap_draws': draws, 'bootstrap_defined_draws': len(samples), 'seed': seed}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--gold', type=Path, required=True, help='JSON list of adjudicated paper records')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    references = json.loads(args.gold.read_text(encoding='utf-8'))
    names = {Path(g['filename']).stem for g in references}
    predictions = [json.loads(p.read_text(encoding='utf-8')) for p in sorted(args.predictions.glob('*.json'))
                   if p.stem in names]
    result = score(predictions, references)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
