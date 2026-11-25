import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('probe_keys',Path(__file__).resolve().parents[1]/'scripts/probe_configured_keys.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class KeyProbeTests(unittest.TestCase):
    def test_duplicate_values_are_probed_once(self):
        self.assertEqual(m.configured_keys({'keys':{'main':'example','backup':'example','third':'other'}}),[('example',['main','backup']),('other',['third'])])

    def test_errors_do_not_echo_provider_message_or_secrets(self):
        import json
        raw=json.dumps({'error':{'message':'SECRET example-key','details':[{'reason':'API_KEY_INVALID','metadata':{'secret':'example-key'}},{'violations':[{'quotaId':'GenerateRequestsPerDayPerProject'}]}]}}).encode()
        result=m.safe_error(raw)
        self.assertEqual(result,{'quota_windows':['per_day'],'credential_reason':'API_KEY_INVALID'})
        self.assertNotIn('example-key',json.dumps(result))

    def test_unknown_error_body_is_not_logged(self):
        self.assertEqual(m.safe_error(b'bad private response'),{'quota_windows':[],'credential_reason':None})


if __name__=='__main__':unittest.main()
