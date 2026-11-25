import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from plan_recovered_additions import prepare
from workflow_io import file_hash


class RecoveredAdditionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'text.json'
        self.source.write_text(json.dumps({'pages':[{'page':1,'text':'A method was evaluated on a dataset.'}]}),encoding='utf-8')
        self.row = {'state':'source_recovered_extraction_pending','live_filename':'a.pdf',
                    'text_path':'text.json','text_sha256':file_hash(self.source),'source_pdf_sha256':'recorded-source-hash'}
        self.inventory = self.root/'inventory.json'
        self.inventory.write_text(json.dumps([{'filename':'a.pdf','paper':{'title':'A scientific article'}}]),encoding='utf-8')

    def run_plan(self):
        (self.root/'manifest.json').write_text(json.dumps({'papers':[self.row]}),encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            prepare(self.root,self.inventory,self.root/'out')

    def test_changed_source_rejected_before_output(self):
        self.source.write_text('{}',encoding='utf-8')
        with self.assertRaises(ValueError):self.run_plan()
        self.assertFalse((self.root/'out').exists())

    def test_page_sequence_rejected(self):
        self.source.write_text(json.dumps({'pages':[{'page':2,'text':'Body'}]}),encoding='utf-8')
        self.row['text_sha256']=file_hash(self.source)
        with self.assertRaises(ValueError):self.run_plan()

    def test_plan_preserves_source_and_does_not_call_api(self):
        before=file_hash(self.source)
        self.run_plan()
        result=json.loads((self.root/'out/manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(result['actual_api_calls'],0)
        self.assertEqual(before,file_hash(self.source))
        doc=json.loads((self.root/'out/documents/a.json').read_text(encoding='utf-8'))
        self.assertEqual(doc['sections'][0]['page'],1)
