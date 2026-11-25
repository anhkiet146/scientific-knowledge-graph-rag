import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/normalization'))
from alias_advisory import materialize

class AliasAdvisoryTests(unittest.TestCase):
    def setUp(self):
        self.case={'candidate_id':'c1','evidence':[{'evidence_id':'p1','page_pdf':1,'text':'Exact source\ntext'}]}
        self.verdict={'candidate_id':'c1','decision':'same_entity','evidence_ids':['p1'],'reason':'A source declaration'}
    def test_preserves_exact_source_and_does_not_authorize_merge(self):
        result=materialize(self.verdict,self.case)
        self.assertEqual(result['evidence'][0]['text'],'Exact source\ntext');self.assertFalse(result['auto_merge'])
    def test_unknown_id_rejected(self):
        with self.assertRaises(ValueError):materialize({**self.verdict,'evidence_ids':['invented']},self.case)
    def test_non_abstention_requires_source(self):
        with self.assertRaises(ValueError):materialize({**self.verdict,'evidence_ids':[]},self.case)
    def test_other_candidate_rejected(self):
        with self.assertRaises(ValueError):materialize({**self.verdict,'candidate_id':'c2'},self.case)
