import copy
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('audit_effects', Path(__file__).resolve().parents[1] / 'scripts/audit_matched_ablation_effects.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(method, context):
    text = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return {'question_id': 1, 'method': method, 'question': 'Q', 'shared_query': 'query',
        'paper_scope': [], 'context': context, 'context_json': text,
        'context_sha256': module.canonical_hash(text), 'context_tokens': 10}


class AblationAuditTests(unittest.TestCase):
    def test_order_change_is_separate_from_evidence_change(self):
        a, b = {'paper_id': 'a.json', 'entity': 'x'}, {'paper_id': 'b.json', 'entity': 'y'}
        pairs, _ = module.audit([row('kg', [a, b]), row('variant', [b, a])], ['kg', 'variant'], [1])
        self.assertTrue(pairs[0]['ordered_context_changed'])
        self.assertFalse(pairs[0]['evidence_set_changed'])
        self.assertEqual(pairs[0]['source_jaccard'], 1)

    def test_empty_context_remains_visible(self):
        pairs, _ = module.audit([row('kg', [{'paper_id': 'a.json'}]), row('variant', [])], ['kg', 'variant'], [1])
        self.assertTrue(pairs[0]['variant_empty'])
        self.assertEqual(pairs[0]['source_jaccard'], 0)

    def test_integrity_grid_scope_and_relation_leak_rejected(self):
        base = row('kg', [{'paper_id': 'a.json'}])
        bad = row('variant', [])
        cases = []
        changed = copy.deepcopy(bad); changed['context_sha256'] = 'invalid'; cases.append([base, changed])
        changed = copy.deepcopy(bad); changed['shared_query'] = 'other'; cases.append([base, changed])
        cases.extend([[base], [base, bad, bad]])
        for records in cases:
            with self.assertRaises(ValueError): module.audit(records, ['kg', 'variant'], [1])
        with self.assertRaises(ValueError):
            module.audit([base, row('kg_no_expansion', [{'paper_id': 'a.json', 'relation': {}}])], ['kg', 'kg_no_expansion'], [1])

    def test_verifier_must_reuse_exact_context(self):
        with self.assertRaises(ValueError):
            module.audit([row('kg', [{'paper_id': 'a.json'}]), row('kg_verified', [])], ['kg', 'kg_verified'], [1])

    def test_changed_plan_cannot_be_attributed_to_ablation(self):
        base, variant = row('kg', []), row('variant', [])
        base['query_plan'] = {'expected_labels': ['Method']}
        variant['query_plan'] = {'expected_labels': ['Author']}
        with self.assertRaisesRegex(ValueError, 'Query plan mismatch'):
            module.audit([base, variant], ['kg', 'variant'], [1])

    def test_partly_missing_plans_rejected_but_legacy_unplanned_data_allowed(self):
        base, variant = row('kg', []), row('variant', [])
        base['query_plan'] = {'expected_labels': ['Method']}
        with self.assertRaisesRegex(ValueError, 'Missing query plan'):
            module.audit([base, variant], ['kg', 'variant'], [1])
        del base['query_plan']
        module.audit([base, variant], ['kg', 'variant'], [1])


if __name__ == '__main__':
    unittest.main()
