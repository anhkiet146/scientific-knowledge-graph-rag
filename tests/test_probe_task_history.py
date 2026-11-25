import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from probe_pending_review_task import previous_probe_tasks
from workflow_io import file_hash

class ProbeHistoryTests(unittest.TestCase):
    def test_attempted_probe_and_rate_limit_not_forgotten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);parent=root/'parent';parent.mkdir();(parent/'contract.json').write_text('{}')
            probe=root/'probe';probe.mkdir();binding=file_hash(parent/'contract.json')
            (probe/'manifest.json').write_text(json.dumps({'parent_contract_sha256':binding,'task':{'question_id':5,'repeat':1,'method':'bm25'}}))
            (probe/'summary.json').write_text(json.dumps({'http_status':429}))
            tasks,limited=previous_probe_tasks(parent)
            self.assertEqual(tasks,{(5,1,'bm25')});self.assertTrue(limited)

    def test_other_run_does_not_block_this_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);parent=root/'parent';parent.mkdir();(parent/'contract.json').write_text('{}')
            probe=root/'probe';probe.mkdir();(probe/'manifest.json').write_text(json.dumps({'parent_contract_sha256':'different'}))
            (probe/'summary.json').write_text(json.dumps({'http_status':429}))
            self.assertEqual(previous_probe_tasks(parent),(set(),False))
