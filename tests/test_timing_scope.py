import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('timing_scope',Path(__file__).resolve().parents[1]/'scripts/audit_timing_scope.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class TimingScopeTests(unittest.TestCase):
    def test_missing_measurement_is_not_zero(self):
        rows,summary=module.analyze([{'question_id':1,'method':'kg'}])
        self.assertIsNone(rows[0]['search_plus_embedding_seconds'])
        self.assertEqual(summary['kg']['stages']['search_seconds']['n'],0)
        self.assertIsNone(summary['kg']['stages']['search_seconds']['mean'])

    def test_partial_sum_does_not_become_end_to_end(self):
        rows,_=module.analyze([{'question_id':1,'method':'vector','search_seconds':.2,'query_embedding_seconds':.3}])
        self.assertEqual(rows[0]['search_plus_embedding_seconds'],.5)
        self.assertIsNone(rows[0]['end_to_end_seconds'])

    def test_bad_durations_and_duplicate_cells_rejected(self):
        for value in [True,-1,float('nan'),float('inf'),'1']:
            with self.assertRaises(ValueError):module.seconds({'s':value},'s')
        row={'question_id':1,'method':'kg'}
        with self.assertRaises(ValueError):module.analyze([row,row])

    def test_spread_is_across_questions_and_singleton_sd_unknown(self):
        self.assertIsNone(module.describe([1])['sample_sd'])
        self.assertEqual(module.describe(list(range(1,21)))['p95_nearest_rank'],19)


if __name__=='__main__':unittest.main()
