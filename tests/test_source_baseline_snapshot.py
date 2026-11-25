import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from run_repaired_source_baselines import verify_source
from workflow_io import file_hash


class SourceBaselineSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'corpus').mkdir()
        self.doc=self.root/'corpus/a.json';self.doc.write_text('{}',encoding='utf-8')
        self.questions=self.root/'questions.py';self.questions.write_text('data=[]',encoding='utf-8')
        self.manifest={'status':'source_only_extraction_and_indices_pending','documents':1,
            'files':[{'path':'corpus/a.json','sha256':file_hash(self.doc)}],
            'questions_sha256':file_hash(self.questions)}
        self.save()

    def save(self):(self.root/'manifest.json').write_text(json.dumps(self.manifest),encoding='utf-8')

    def test_added_source_is_not_silently_indexed(self):
        (self.root/'corpus/b.json').write_text('{}',encoding='utf-8')
        with self.assertRaises(ValueError):verify_source(self.root)

    def test_changed_source_rejected(self):
        self.doc.write_text('{"changed":true}',encoding='utf-8')
        with self.assertRaises(ValueError):verify_source(self.root)

    def test_changed_questions_rejected(self):
        self.questions.write_text('data=[1]',encoding='utf-8')
        with self.assertRaises(ValueError):verify_source(self.root)

    def test_matching_source_snapshot_is_accepted(self):
        self.assertEqual(verify_source(self.root)['documents'],1)
