import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/extraction'))
from chunk_contract import scoped_task_schema
from chunk_runner import contract


class ScopedSchemaTests(unittest.TestCase):
    def test_only_selected_ids_in_provider_schema(self):
        base=contract()[0]['schema'];before=copy.deepcopy(base)
        task={'scope_ids':['a'],'context_ids':['b']}
        result=scoped_task_schema(base,task,{'items':[{'id':x} for x in ['a','b','c']]})
        for kind in ('entities','relations'):
            self.assertEqual(result['properties'][kind]['items']['properties']['evidence_ids']['items']['enum'],['a','b'])
            self.assertEqual(result['properties'][kind]['items']['properties']['evidence_ids']['maxItems'],16)
        self.assertEqual(result['properties']['completion']['properties']['remaining_scope_ids']['items']['enum'],['a'])
        self.assertEqual(base,before)

    def test_unknown_evidence_cannot_be_authorized(self):
        with self.assertRaises(ValueError):
            scoped_task_schema(contract()[0]['schema'],{'scope_ids':['missing'],'context_ids':[]},{'items':[]})
