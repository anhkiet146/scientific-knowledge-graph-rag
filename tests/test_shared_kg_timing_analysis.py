import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_shared_kg_timings import analyze, METHODS


class SharedKGTimingTests(unittest.TestCase):
    def rows(self):
        return [dict(method=m,question_id=q,repeat=r,retrieval_wall_seconds=.01,
                     context_sha256=f'{m}-{q}')
                for m in METHODS for q in range(1,46) for r in range(1,6)]

    def test_repeats_are_not_independent_questions_and_holm_null(self):
        result=analyze(self.rows(),draws=100)
        self.assertEqual(result['records'],675)
        for test in result['paired_tests']:
            self.assertEqual(test['n_questions'],45)
            self.assertEqual(test['holm_adjusted_p'],1)

    def test_incomplete_grid_rejected(self):
        with self.assertRaises(ValueError):analyze(self.rows()[:-1],draws=100)

    def test_changed_context_rejected(self):
        rows=self.rows();rows[0]['context_sha256']='modified'
        with self.assertRaises(ValueError):analyze(rows,draws=100)

    def test_duplicate_and_nonfinite_rejected(self):
        rows=self.rows()
        with self.assertRaises(ValueError):analyze(rows+[rows[0]],draws=100)
        rows[0]['retrieval_wall_seconds']=float('nan')
        with self.assertRaises(ValueError):analyze(rows,draws=100)


if __name__=='__main__':unittest.main()
