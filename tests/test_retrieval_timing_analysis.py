import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_fair_retrieval_timings import analyze


class RetrievalTimingAnalysisTests(unittest.TestCase):
    def rows(self):return [{'method':m,'question_id':q,'repeat':r,'query_embedding_seconds':0,
        'search_seconds':q,'packing_seconds':0,'retrieval_wall_seconds':q,'context_sha256':m+str(q)}
        for m in ['bm25','vector'] for q in [1,2] for r in [1,2,3,4,5]]
    def evaluate(self,rows):return analyze(rows,question_ids=(1,2),draws=100)

    def test_question_is_the_inference_unit(self):
        result=self.evaluate(self.rows())
        self.assertEqual(result['paired_wall_time']['n_questions'],2)
        self.assertEqual(result['paired_wall_time']['mean_difference'],0)
        self.assertEqual(result['paired_wall_time']['paired_sign_flip_p'],1)
        self.assertEqual(result['paired_wall_time']['bootstrap_95_ci'],[0,0])

    def test_missing_repeat_cannot_be_excluded_silently(self):
        with self.assertRaises(ValueError):self.evaluate(self.rows()[:-1])

    def test_invalid_duration_is_not_zero_filled(self):
        for invalid in [None,True,-1,float('nan')]:
            rows=self.rows();rows[0]['search_seconds']=invalid
            with self.assertRaises(ValueError):self.evaluate(rows)

    def test_changed_context_cannot_be_pooled(self):
        rows=self.rows();rows[0]['context_sha256']='changed'
        with self.assertRaises(ValueError):self.evaluate(rows)

    def test_stage_sum_must_match_wall(self):
        rows=self.rows();rows[0]['retrieval_wall_seconds']=99
        with self.assertRaises(ValueError):self.evaluate(rows)
