import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('chunk_plan',ROOT/'scripts/plan_chunked_extraction.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class ChunkPlanTests(unittest.TestCase):
    def test_scope_is_complete_nonoverlapping_and_bound_to_original_evidence(self):
        document={'title':'Source title','raw_header':'Author: Alice Doe.',
                  'sections':[{'category':'pdf_page','page':1,'content':'\n'.join(f'Original source line {i} with evidence.' for i in range(65))}]}
        result=module.plan(document,max_items=20)
        scope=[i for t in result['tasks'] for i in t['scope_ids']]
        self.assertEqual(len(scope),len(set(scope)))
        self.assertEqual(set(scope),{i['id'] for i in result['catalog']['items']})
        for task in result['tasks'][1:]:self.assertLessEqual(len(task['scope_ids']),20)
        self.assertEqual(result['actual_api_calls'],0)

    def test_bad_limit_is_rejected_without_any_execution(self):
        with self.assertRaises(ValueError):module.plan({},max_items=0)
