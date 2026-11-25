import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/evaluation'))
from failure_aware_statistics import summarize


class FailureAwareTests(unittest.TestCase):
    def fixture(self):
        return [{'method':m,'question_id':q,'repeat':r,'generation_status':'success','assessment_source':'independent_human',
            'correctness':1.,'attempt_seconds':3.} for m in ('kg','bm25') for q in (1,2) for r in (1,2)]
    def calculate(self,rows):return summarize(rows,methods=['kg','bm25'],question_ids=[1,2],repeats=[1,2],draws=100)
    def test_failures_reduce_utility_without_zero_latency_or_dropped_question(self):
        rows=self.fixture();rows[0].update(generation_status='failed',attempt_seconds=7.);del rows[0]['correctness']
        result=self.calculate(rows);kg=next(r for r in result['summary'] if r['method']=='kg')
        self.assertEqual(kg['failure_penalized_mean'],.75);self.assertEqual(kg['conditional_success_mean'],1.)
        self.assertEqual(result['attempt_timing']['kg']['failed']['mean_seconds'],7.)
        self.assertEqual(result['paired_tests'][0]['n_questions'],2)
    def test_missing_duplicate_or_ambiguous_status_rejected(self):
        for mutation in ('missing','duplicate','ambiguous'):
            rows=self.fixture()
            if mutation=='missing':rows.pop()
            elif mutation=='duplicate':rows.append(rows[0])
            else:del rows[0]['generation_status'];rows[0]['error']='unknown stage'
            with self.assertRaises(ValueError):self.calculate(rows)
    def test_missing_scores_mixed_sources_or_nonfinite_time_rejected(self):
        for mutation in ('score','source','time'):
            rows=self.fixture()
            if mutation=='score':del rows[0]['correctness']
            elif mutation=='source':rows[0]['assessment_source']='llm_proxy'
            else:rows[0]['attempt_seconds']=float('nan')
            with self.assertRaises(ValueError):self.calculate(rows)
