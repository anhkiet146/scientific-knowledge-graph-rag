import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src/retrieval'), str(ROOT/'src/extraction')]
import claim_verification as verifier
from workflow_io import atomic_json, file_hash


def cases():
    def case(name, draft, context, quote, accepted, group, **changes):
        claim = {'text': draft, 'quote': quote, 'context_index': 0, 'supported': True, 'atomic': True}
        claim.update(changes)
        return {'case_id': name, 'group': group, 'draft': draft, 'contexts': [context],
                'verdict': {'claims': [claim]}, 'expected_structural_acceptance': accepted}
    return [
        case('supported_sentence', 'Model A scored 80 percent.', {'text': 'Model A scored 80 percent.'}, 'Model A scored 80 percent.', True, 'supported_control'),
        case('supported_short_name', 'Phan Van Ut', {'author': 'Phan Van Ut'}, 'Phan Van Ut', True, 'supported_control'),
        case('rewritten_draft', 'Model A scored 80 percent.', {'text': 'Model A scored 80 percent.'}, 'Model A scored 80 percent.', False, 'structural_guard', text='Model A scored 90 percent.'),
        case('json_key_quote', 'Phan Van Ut', {'Phan Van Ut': 'unknown'}, 'Phan Van Ut', False, 'structural_guard'),
        case('boolean_index', 'Phan Van Ut', {'author': 'Phan Van Ut'}, 'Phan Van Ut', False, 'structural_guard', context_index=True),
        case('out_of_range_index', 'Phan Van Ut', {'author': 'Phan Van Ut'}, 'Phan Van Ut', False, 'structural_guard', context_index=2),
        case('short_number', '70', {'text': '70'}, '70', False, 'structural_guard'),
        case('atomicity_missing', 'Phan Van Ut', {'author': 'Phan Van Ut'}, 'Phan Van Ut', False, 'structural_guard', atomic=False),
        case('marked_unsupported', 'Phan Van Ut', {'author': 'Phan Van Ut'}, 'Phan Van Ut', False, 'structural_guard', supported=False),
        case('wrong_number_with_real_quote', 'Model A scored 90 percent.', {'text': 'Model A scored 80 percent.'}, 'Model A scored 80 percent.', True, 'known_semantic_gap'),
        case('wrong_negation_with_real_quote', 'Treatment improved growth.', {'text': 'Treatment did not improve growth.'}, 'Treatment did not improve growth.', True, 'known_semantic_gap'),
        case('wrong_object_with_real_quote', 'Model B scored 80 percent.', {'text': 'Model A scored 80 percent.'}, 'Model A scored 80 percent.', True, 'known_semantic_gap'),
        case('wrong_sign_with_real_quote', 'The change was -70 percent.', {'text': 'The change was +70 percent.'}, 'The change was +70 percent.', True, 'known_semantic_gap'),
        case('metadata_value_used_as_evidence', 'Trial supported the claim.', {'paper_id': 'Trial supported the claim.'}, 'Trial supported the claim.', True, 'known_semantic_gap'),
        case('non_atomic_list_marked_atomic', 'Model A scored 80 percent; Model B scored 90 percent.', {'text': 'Model A scored 80 percent; Model B scored 90 percent.'}, 'Model A scored 80 percent; Model B scored 90 percent.', True, 'known_semantic_gap'),
    ]


def evaluate():
    results = []
    for case in cases():
        answer, audit = verifier.filter_claims_v2(case['draft'], case['contexts'], case['verdict'])
        accepted = any(item['accepted'] for item in audit)
        results.append({**case, 'filtered_answer': answer, 'claim_audit': audit,
            'actual_structural_acceptance': accepted,
            'matches_expected_implementation_behavior': accepted == case['expected_structural_acceptance']})
    return results


def run(output):
    if output.exists(): raise ValueError('Fresh output required')
    results = evaluate()
    if not all(r['matches_expected_implementation_behavior'] for r in results):
        raise ValueError('Verifier behavior changed; inspect fixtures before reporting')
    output.mkdir(parents=True)
    with (output/'synthetic_cases.jsonl').open('w', encoding='utf-8') as f:
        for row in results: f.write(json.dumps(row, ensure_ascii=False)+'\n')
    summary = {'synthetic_cases': len(results), 'groups': dict(Counter(r['group'] for r in results)),
        'known_gap_cases_structurally_accepted': sum(r['actual_structural_acceptance'] for r in results if r['group']=='known_semantic_gap'),
        'implementation_behavior_matches_expectations': True, 'actual_api_calls': 0,
        'qa_quality_measured': False, 'independent_annotation_performed': False,
        'limits': 'Handcrafted developer diagnostics with deliberately incorrect supplied model verdicts. No LLM was queried. Counts are not empirical hallucination rates, faithfulness scores, or estimated verifier accuracy.'}
    atomic_json(output/'summary.json', summary)
    sources = [Path(__file__), Path(verifier.__file__)]
    atomic_json(output/'manifest.json', {'code_sha256': {p.name: file_hash(p) for p in sources},
        'cases_sha256': file_hash(output/'synthetic_cases.jsonl'), 'active_verifier_modified': False})
    for path in sources: shutil.copy2(path, output/path.name)
    print(json.dumps(summary, indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    run(**vars(parser.parse_args()))
