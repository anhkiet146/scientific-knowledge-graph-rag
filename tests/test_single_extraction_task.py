import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from run_one_extraction_task import ensure_unreserved,run


class SingleTaskTests(unittest.TestCase):
    def test_reserved_task_rejected_across_policy_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'request.json').write_text(json.dumps({'source_sha256':'s','task_sha256':'t','policy_sha256':'old'}),encoding='utf-8')
            with self.assertRaises(ValueError):ensure_unreserved(root,'s','t')
            ensure_unreserved(root,'s','different_task')

    def test_failure_log_does_not_store_exception_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.json'
            source.write_text(json.dumps({'title':'Study','sections':[]}),encoding='utf-8')
            with patch('run_one_extraction_task._key',return_value='secret-key'),patch('run_one_extraction_task.Client') as client,contextlib.redirect_stdout(io.StringIO()):
                client.return_value.generate.side_effect=RuntimeError('secret-key')
                run(source,'metadata',root/'history',root/'output',root/'unused',True)
            outcome=(root/'output/outcome.json').read_text(encoding='utf-8')
            self.assertNotIn('secret-key',outcome)
            self.assertEqual(json.loads(outcome)['api_attempts'],1)
            self.assertFalse(json.loads(outcome)['automatic_retry'])

    def test_preflight_has_no_provider_request(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.json'
            source.write_text(json.dumps({'title':'Study','sections':[]}),encoding='utf-8')
            with patch('run_one_extraction_task.Client') as client:
                run(source,'metadata',root/'history',root/'output',root/'unused',False)
                client.assert_not_called()
            self.assertFalse((root/'output/request.json').exists())
