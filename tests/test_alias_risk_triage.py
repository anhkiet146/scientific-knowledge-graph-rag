import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from triage_alias_candidates import risk_flags

class AliasRiskTests(unittest.TestCase):
    def test_versions_and_model_sizes_are_not_hidden(self):
        self.assertIn('numeric_or_version_difference',risk_flags('Software 1.0','Software 2.0'))
        self.assertIn('variant_or_condition_difference',risk_flags('Model-Small','Model-Large'))

    def test_negation_and_complexity_are_flagged(self):
        self.assertIn('negation_difference',risk_flags('Uniform bound','Non-uniform bound'))
        self.assertIn('complexity_expression_difference',risk_flags('O(n) algorithm','O(n log n) algorithm'))

    def test_punctuation_alone_is_not_a_qualifier_difference(self):
        self.assertEqual(risk_flags('Gas chromatography-mass spectrometry','Gas chromatography–mass spectrometry'),[])
