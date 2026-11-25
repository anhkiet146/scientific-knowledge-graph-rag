from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/evaluation'))
from failure_aware_statistics import summarize


def fixtures():
    return [{'method':m,'question_id':q,'repeat':r,'generation_status':'success',
        'assessment_source':'independent_human','correctness':float(q==2),'attempt_seconds':1.}
        for m in ['kg','bm25'] for q in [1,2] for r in [1,2,3,4,5]]


def analyze(rows,draws=100):
    return summarize(rows,methods=['kg','bm25'],question_ids=[1,2],repeats=[1,2,3,4,5],draws=draws)


class StatisticsReviewTests(unittest.TestCase):
    def test_repeats_do_not_inflate_inference_unit_and_ci_is_repeatable(self):
        first=analyze(fixtures());second=analyze(fixtures())
        self.assertEqual(first,second)
        self.assertEqual(first['paired_tests'][0]['n_questions'],2)
        self.assertEqual(first['paired_tests'][0]['paired_sign_flip_p'],1)
        self.assertEqual(first['summary'][0]['n_questions'],2)
        self.assertEqual(first['summary'][0]['repeats_per_question'],5)
        self.assertEqual(first['summary'][0]['bootstrap_95_ci_failure_penalized_mean'],[0,1])

    def test_boolean_float_ids_and_bad_draw_counts_are_rejected(self):
        for field,value in [('question_id',True),('question_id',1.),('repeat',True),('repeat',1.)]:
            rows=fixtures();rows[0][field]=value
            with self.assertRaises(ValueError):analyze(rows)
        for value in [True,100.,'100']:
            with self.assertRaises(ValueError):analyze(fixtures(),draws=value)

    def test_ungraded_success_and_unstarted_attempt_are_not_zero_filled(self):
        rows=fixtures();rows[0]['correctness']=None
        with self.assertRaises(ValueError):analyze(rows)
        rows=fixtures();rows[0]['generation_status']='not_started'
        with self.assertRaises(ValueError):analyze(rows)

    def test_holm_adjusted_p_is_bounded_and_not_smaller_than_raw(self):
        result=analyze(fixtures())
        for test in result['paired_tests']:
            self.assertLessEqual(test['paired_sign_flip_p'],test['holm_adjusted_p'])
            self.assertLessEqual(test['holm_adjusted_p'],1)


if __name__=='__main__':unittest.main()
