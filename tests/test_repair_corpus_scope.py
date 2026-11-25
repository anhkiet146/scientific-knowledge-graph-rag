from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from repair_review_corpus_scope import require_source_phrase


class CorpusSourceCheckTests(unittest.TestCase):
    def test_topic_evidence_keeps_page_and_offset(self):
        result=require_source_phrase([{'page':7,'text':'The VLFFD dataset was introduced.'}],'VLFFD')
        self.assertEqual(result[0]['page'],7)
        self.assertEqual(result[0]['start'],4)
        self.assertIn('VLFFD',result[0]['excerpt'])

    def test_missing_topic_is_not_filled_from_reference(self):
        with self.assertRaises(ValueError):
            require_source_phrase([{'page':1,'text':'An unrelated study.'}],'CuRLA')

    def test_topic_search_is_case_insensitive(self):
        self.assertEqual(len(require_source_phrase([{'page':1,'text':'curla'}],'CuRLA')),1)
