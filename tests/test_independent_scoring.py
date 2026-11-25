import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/evaluation'))
from score_independent_extraction import score


def fixture():
    return {'filename': 'paper.pdf', 'source_sha256': '0' * 64,
            'annotation_status': 'adjudicated', 'annotators': ['human_A', 'human_B'],
            'adjudication_log': [{'decision': 'independent labels agree'}],
            'extraction_result': {'entities': [{'id': 'Learner A', 'type': 'Method'},
                                               {'id': 'Task X', 'type': 'Concept'}],
                                  'relations': [{'source': 'Learner A', 'type': 'USED_FOR', 'target': 'Task X'}]}}


class IndependentScoringTests(unittest.TestCase):
    def test_pending_and_source_mismatch_cannot_be_scored(self):
        gold = fixture()
        gold['annotation_status'] = 'pending'
        with self.assertRaises(ValueError):
            score([], [gold], draws=10)
        gold = fixture()
        predicted = copy.deepcopy(gold)
        predicted['source_sha256'] = '1' * 64
        with self.assertRaises(ValueError):
            score([predicted], [gold], draws=10)

    def test_missing_paper_is_false_negatives_not_silently_dropped(self):
        result = score([], [fixture()], draws=10)
        self.assertEqual(result['missing_predictions'], 1)
        self.assertEqual(result['entities']['micro']['fn'], 2)
        self.assertEqual(result['entities']['micro']['recall'], 0)
        self.assertIsNone(result['entities']['micro']['precision'])

    def test_duplicate_predictions_count_as_extra_false_positives(self):
        gold = fixture()
        predicted = copy.deepcopy(gold)
        predicted['extraction_result']['entities'].append({'id': 'Learner A', 'type': 'Method'})
        result = score([predicted], [gold], draws=10)
        self.assertEqual(result['entities']['micro']['tp'], 2)
        self.assertEqual(result['entities']['micro']['fp'], 1)
        self.assertEqual(result['relations']['micro']['f1'], 1)

    def test_reversed_or_out_of_schema_relation_is_not_accepted(self):
        gold = fixture()
        predicted = copy.deepcopy(gold)
        relation = predicted['extraction_result']['relations'][0]
        relation['source'], relation['target'] = relation['target'], relation['source']
        with self.assertRaises(ValueError):
            score([predicted], [gold], draws=10)

    def test_source_spelling_is_not_fuzzy_matched(self):
        gold = fixture()
        predicted = copy.deepcopy(gold)
        predicted['extraction_result']['entities'][0]['id'] = 'Learner B'
        predicted['extraction_result']['relations'][0]['source'] = 'Learner B'
        result = score([predicted], [gold], draws=10)
        self.assertEqual(result['entities']['micro']['tp'], 1)
        self.assertEqual(result['relations']['micro']['tp'], 0)

    def test_bootstrap_is_reproducible_by_paper(self):
        gold = fixture()
        self.assertEqual(score([gold], [gold], draws=30), score([gold], [gold], draws=30))
