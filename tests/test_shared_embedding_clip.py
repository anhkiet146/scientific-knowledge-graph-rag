from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/evaluation'))
from fair_runtime import clip_embedding_inputs


class SimpleTokenizer:
    def num_special_tokens_to_add(self,pair=False):return 2
    def __call__(self,text,add_special_tokens=False,truncation=False):
        assert truncation is False
        return {'input_ids':list(text)+(list('[]') if add_special_tokens else [])}
    def decode(self,ids,**kwargs):return ''.join(ids)


class SharedEmbeddingClipTests(unittest.TestCase):
    def test_budget_includes_special_tokens_and_reports_loss(self):
        result,audit=clip_embedding_inputs(SimpleTokenizer(),['abcdef','ab'],6)
        self.assertEqual(result,['abcd','ab'])
        self.assertTrue(audit[0]['truncated'])
        self.assertFalse(audit[1]['truncated'])
        self.assertEqual(audit[0]['tokens_after_with_special'],6)

    def test_input_and_limits_are_validated(self):
        with self.assertRaises(ValueError):clip_embedding_inputs(SimpleTokenizer(),['x'],2)
        with self.assertRaises(ValueError):clip_embedding_inputs(SimpleTokenizer(),[None],6)
