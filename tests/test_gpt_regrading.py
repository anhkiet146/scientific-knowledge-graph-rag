from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
import io
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from regrade_qa_openai import body_for,response_text,safe_error,credentials


class GPTRegradingTests(unittest.TestCase):
    def test_non_completed_response_is_not_a_grade(self):
        with self.assertRaises(ValueError):response_text({'status':'incomplete','output':[]})
        self.assertEqual(response_text({'status':'completed','output':[{'type':'message',
            'content':[{'type':'output_text','text':'{}'}]}]}),'{}')

    def test_request_has_no_credentials_and_no_false_temperature_zero(self):
        body=body_for('case','gpt-5.5')
        self.assertNotIn('temperature',body);self.assertFalse(body['store'])
        self.assertEqual(body['reasoning']['effort'],'low')

    def test_errors_do_not_echo_sensitive_provider_messages(self):
        err=urllib.error.HTTPError('https://api.openai.com',401,'SECRET_KEY',{},
            io.BytesIO(b'{"error":{"code":"invalid_api_key","message":"SECRET_KEY"}}'))
        result=safe_error(err)
        self.assertEqual(result['provider_error_code'],'invalid_api_key');self.assertNotIn('SECRET_KEY',str(result))

    def test_config_is_read_without_executing_it(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'config.py';p.write_text("OPENAI_API_KEY='synthetic'\nOPENAI_JUDGE_MODEL='gpt-5.5'\nraise RuntimeError('must not execute')")
            self.assertEqual(credentials(p),('synthetic','gpt-5.5'))


if __name__=='__main__':unittest.main()
