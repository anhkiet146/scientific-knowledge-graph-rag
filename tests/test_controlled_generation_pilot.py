import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/evaluation'))
from controlled_generation_pilot import load_contexts,BASE_METHODS,parse_verdict
from workflow_io import canonical_hash


class ControlledPilotTests(unittest.TestCase):
    def test_verdict_transport_wrapper_does_not_change_json_contents(self):
        plain='{"claims": [{"text":"Source claim","supported":true,"context_index":0,"quote":"Exact source quote"}]}'
        first,wrapped=parse_verdict(plain);second,wrapped_second=parse_verdict('```json\n'+plain+'\n```')
        self.assertFalse(wrapped);self.assertTrue(wrapped_second);self.assertEqual(first,second)
    def test_verdict_does_not_repair_prose_or_duplicate_json_fields(self):
        for raw in ('Here is JSON: {"claims":[]}', '{"claims":[],"claims":[{}]}','```json\n{"claims":[]}\n``` trailing prose'):
            with self.assertRaises(ValueError):parse_verdict(raw)
    def rows(self):
        text=json.dumps([{'text':'Exact source evidence.'}])
        return [{'question_id':1,'method':m,'question':'Who wrote the study?','context':json.loads(text),
            'context_json':text,'context_sha256':canonical_hash(text),'context_tokens':10} for m in BASE_METHODS+('kg_verified',)]
    def load(self,rows):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'contexts.jsonl';path.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            return load_contexts(path,1)
    def test_all_eight_methods_and_exact_paired_context_required(self):
        self.assertEqual(len(self.load(self.rows())),8)
        rows=self.rows();rows[-1]['context']=[{'text':'Different source'}];rows[-1]['context_json']=json.dumps(rows[-1]['context']);rows[-1]['context_sha256']=canonical_hash(rows[-1]['context_json'])
        with self.assertRaises(ValueError):self.load(rows)
    def test_missing_duplicate_or_modified_context_rejected(self):
        for mutation in ('missing','duplicate','modified'):
            rows=self.rows()
            if mutation=='missing':rows.pop()
            elif mutation=='duplicate':rows.append(rows[0])
            else:rows[0]['context'][0]['text']='Changed'
            with self.assertRaises(ValueError):self.load(rows)
