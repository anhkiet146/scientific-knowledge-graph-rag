from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/extraction'))
from reextract_review import validate_extraction


class EvidenceLimitTests(unittest.TestCase):
    def test_too_many_quotes_is_distinguished_from_ungrounded(self):
        text='The method uses a valid scientific procedure.'
        sections=[{'section_id':'s1','text':text,'kind':'body'}]
        entity={'id':'e1','name':'Method','type':'Method','description':'Description',
                'evidence':[{'section_id':'s1','text':text}]*17}
        cleaned,issues=validate_extraction({'entities':[entity],'relations':[]},sections)
        self.assertEqual(cleaned['entities'],[])
        self.assertEqual(issues[0]['reason'],'evidence_limit_exceeded')

    def test_sixteen_quotes_do_not_trigger_count_rejection(self):
        text='The method uses a valid scientific procedure.'
        entity={'id':'e1','name':'Method','type':'Method','description':'Description',
                'evidence':[{'section_id':'s1','text':text}]*16}
        cleaned,issues=validate_extraction({'entities':[entity],'relations':[]},[{'section_id':'s1','text':text}])
        self.assertEqual(len(cleaned['entities']),1)
        self.assertEqual(issues,[])
