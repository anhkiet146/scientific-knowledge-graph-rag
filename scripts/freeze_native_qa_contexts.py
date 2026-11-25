"""Freeze native retrieval evidence and an explicit missing-context policy."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src/extraction'), str(ROOT / 'src/evaluation')]
from workflow_io import atomic_json, canonical_hash, file_hash
from context_budget import pack_v2


def evidence_record(item):
    return {'entity': {'name':item['entity_name'], 'type':item['entity_type'],
                       'description':item.get('entity_desc', '')},
            'source_papers':item.get('source_papers', []),
            'source_paper_keys':item.get('source_paper_keys', []),
            'connections':item.get('connections', [])}


def prepare(retrieval, tokenizer_cache, output):
    if output.exists():
        raise ValueError('Fresh output required')
    os.environ['TIKTOKEN_CACHE_DIR'] = str(tokenizer_cache.resolve())
    import tiktoken
    import tiktoken.load
    def offline(url):
        raise RuntimeError('Tokenizer download disabled; provide cached tokenizer')
    tiktoken.load.read_file = offline
    encoder = tiktoken.get_encoding('o200k_base')
    data = json.loads(retrieval.read_text(encoding='utf-8'))
    if data['database'] != 'graphrag-review-482' or data['generation_api_calls'] != 0:
        raise ValueError('Expected isolated native retrieval diagnostic')
    cases = data['results']
    if sorted(r['question_id'] for r in cases) != list(range(1,46)):
        raise ValueError('45 unique questions required')
    rows = []
    for case in cases:
        records = [evidence_record(item) for item in case['selected']]
        context, text, tokens, audit = pack_v2(records, lambda text:encoder.encode(text, disallowed_special=()), 2000)
        state = 'ready_ungraded' if context else 'no_context_abstain_without_api'
        rows.append({'question_id':case['question_id'], 'question':case['question'],
                     'method':'kg_native', 'context':context, 'context_json':text,
                     'context_sha256':canonical_hash(text), 'context_tokens':tokens,
                     'packing_audit':audit, 'state':state, 'quality_score':None,
                     'paper_scope':case['paper_scope']})
    output.mkdir(parents=True)
    path = output / 'contexts.jsonl'
    path.write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in rows), encoding='utf-8')
    policy = {'empty_context':'abstain_without_api', 'missing_quality_score':None,
              'provider_failure':'stop_no_retry_no_key_rotation',
              'unscoped_question':'retain_and_flag_not_automatically_wrong',
              'out_of_corpus':'retain_in_45_question_inventory_no_gold_injection',
              'expert_grading':'pending_not_performed', 'generation_prompt':'shared generation_prompt from snapshot_benchmark',
              'comparison_status':'native diagnostic only; regenerate baselines with identical scope policy before comparisons',
              'model':'gemini-2.5-flash', 'temperature':0, 'thinking_budget':0, 'max_output_tokens':1024}
    atomic_json(output / 'policy.json', policy)
    manifest = {'contexts_sha256':file_hash(path), 'retrieval_sha256':file_hash(retrieval),
                'policy_sha256':file_hash(output / 'policy.json'), 'code_sha256':file_hash(Path(__file__)),
                'context_limit':2000, 'tokenizer':'o200k_base', 'packing':'pack_v2_whole_records',
                'rows':45, 'ready':sum(r['state']=='ready_ungraded' for r in rows),
                'abstain_questions':[r['question_id'] for r in rows if r['state']!='ready_ungraded'],
                'actual_api_calls':0, 'quality_scores_computed':False}
    atomic_json(output / 'manifest.json', manifest)
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('retrieval', 'tokenizer-cache', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    prepare(**vars(parser.parse_args()))
