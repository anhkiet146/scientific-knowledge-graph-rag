import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/evaluation'))
from budgeted_gemini_text import BudgetedText

class FailureLoggingTests(unittest.TestCase):
    def check_failure(self,message):
        with tempfile.TemporaryDirectory() as tmp:
            def transport(body):raise RuntimeError(message)
            provider=BudgetedText('private-dummy-key',Path(tmp),max_calls=1,transport=transport)
            with self.assertRaises(RuntimeError):asyncio.run(provider('test'))
            text=(Path(tmp)/'0001/outcome.json').read_text()
            self.assertNotIn('private-dummy-key',text)
            self.assertNotIn('sensitive detail',text)
            self.assertEqual(provider.calls,1)
            return json.loads(text)

    def test_known_http_status_is_retained(self):
        self.assertEqual(self.check_failure('Gemini HTTP 429; no automatic retry')['http_status'],429)

    def test_unknown_error_does_not_log_message(self):
        self.assertIsNone(self.check_failure('private-dummy-key sensitive detail')['http_status'])
