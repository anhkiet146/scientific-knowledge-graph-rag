from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/evaluation'))
from common_context_preflight import bounded


class CommonContextTests(unittest.TestCase):
    def test_budget_counts_serialization_overhead_and_preserves_source(self):
        chunks=[{'source':{'text':'source α'}},{'source':{'text':'another source'}}]
        _,text,_=bounded(chunks,[(0,1.)],lambda text:list(text),1000)
        rows,serialized,n=bounded(chunks,[(0,1.),(1,.5)],lambda text:list(text),len(text))
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['text'],'source α')
        self.assertEqual(serialized,text);self.assertEqual(n,len(text))
    def test_too_small_budget_does_not_clip_or_invent_source(self):
        chunks=[{'source':{'text':'long original source'}}]
        self.assertEqual(bounded(chunks,[(0,1.)],list,2),([],'[]',2))
        with self.assertRaises(ValueError):bounded(chunks,[(0,1.)],list,1)
    def test_negative_boolean_or_duplicate_chunk_ids_rejected(self):
        chunks=[{'source':{'text':'source'}}]
        for hits in ([(-1,1.)],[(True,1.)],[(0,1.),(0,.9)]):
            with self.assertRaises(ValueError):bounded(chunks,hits,list,1000)
