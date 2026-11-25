import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from import_neo4j_snapshot import load_plan
from workflow_io import file_hash


class ImportIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.records = {'papers': [], 'entities': [], 'mentions': [], 'relations': []}

    def write(self, target='graphrag-review-482'):
        path = self.root / 'records.json'
        path.write_text(json.dumps(self.records), encoding='utf-8')
        self.manifest = {'target_database':target, 'live_database_allowed':False,
                         'counts':{k:len(v) for k,v in self.records.items()},
                         'records_sha256':file_hash(path)}
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def test_live_target_rejected(self):
        self.write('neo4j')
        with self.assertRaises(ValueError): load_plan(self.root)

    def test_modified_records_rejected(self):
        self.write()
        (self.root / 'records.json').write_text('{}', encoding='utf-8')
        with self.assertRaises(ValueError): load_plan(self.root)

    def test_dynamic_label_rejected(self):
        self.records['entities'] = [{'label':'Author` DELETE n'}]
        self.write()
        with self.assertRaises(ValueError): load_plan(self.root)

    def test_counts_mismatch_rejected(self):
        self.write()
        self.manifest['counts']['papers'] = 482
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        with self.assertRaises(ValueError): load_plan(self.root)
