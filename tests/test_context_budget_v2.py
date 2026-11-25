import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/evaluation'))
from context_budget import pack,pack_v2

class PackingV2Tests(unittest.TestCase):
    def test_oversized_first_does_not_hide_later_evidence(self):
        records=[{'text':'x'*100},{'text':'Author Y'}]
        result,text,count,audit=pack_v2(records,list,40)
        self.assertEqual(result,[records[1]]);self.assertLessEqual(count,40)
        self.assertFalse(audit[0]['accepted']);self.assertTrue(audit[1]['accepted'])
        self.assertEqual(pack(records,list,40)[0],[])

    def test_does_not_cut_claims_or_modify_records(self):
        record={'value':'-70%','source':'Paper 1'}
        self.assertEqual(pack_v2([record],list,10)[0],[])
        self.assertEqual(record,{'value':'-70%','source':'Paper 1'})

    def test_stable_order_and_empty_budget(self):
        records=[{'x':1},{'x':2}]
        self.assertEqual(pack_v2(records,list,100)[0],records)
        with self.assertRaises(ValueError):pack_v2([],list,1)
