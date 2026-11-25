import asyncio
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/evaluation'))
from budgeted_gemini_text import BudgetedText
from workflow_io import read_json


class BudgetedTextTests(unittest.IsolatedAsyncioTestCase):
    async def test_larger_budget_requires_controlled_scope_and_still_has_ceiling(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):BudgetedText('test',tmp,max_calls=3)
            with self.assertRaises(ValueError):BudgetedText('test',tmp,max_calls=17,scope='controlled_generation_pilot')
    async def test_json_verifier_mode_and_output_limit_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            captured=[]
            def transport(body):captured.append(body);return self.response(body)
            client=BudgetedText('test',tmp,max_calls=1)
            client.transport=transport
            await client('verify',json_mode=True,output_token_limit=4096)
            self.assertEqual(captured[0]['generationConfig']['responseMimeType'],'application/json')
            self.assertEqual(captured[0]['generationConfig']['maxOutputTokens'],4096)
    def response(self,body):return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'official plain tuple output'}]}}]}
    async def test_no_json_schema_rewrite_and_no_key_in_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            captured=[]
            def transport(body):captured.append(body);return self.response(body)
            client=BudgetedText('synthetic-secret',tmp,max_calls=1,transport=transport)
            text=await client('source',system_prompt='upstream instructions',history_messages=[{'role':'assistant','content':'prior'}])
            self.assertEqual(text,'official plain tuple output')
            self.assertEqual(captured[0]['contents'][0]['role'],'model')
            self.assertNotIn('responseSchema',captured[0]['generationConfig'])
            for path in Path(tmp).rglob('*.json'):self.assertNotIn('synthetic-secret',path.read_text())
    async def test_concurrent_budget_never_sends_more_than_ceiling(self):
        with tempfile.TemporaryDirectory() as tmp:
            sent=[]
            def transport(body):sent.append(body);return self.response(body)
            client=BudgetedText('test',tmp,max_calls=1,transport=transport)
            results=await asyncio.gather(client('one'),client('two'),return_exceptions=True)
            self.assertEqual(len(sent),1);self.assertEqual(sum(isinstance(r,RuntimeError) for r in results),1)
    async def test_failed_request_is_journalled_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            sent=[]
            def transport(body):sent.append(body);raise OSError('unknown outcome')
            client=BudgetedText('test',tmp,max_calls=1,transport=transport)
            with self.assertRaises(RuntimeError):await client('one')
            with self.assertRaises(RuntimeError):await client('one')
            self.assertEqual(len(sent),1)
            self.assertEqual(read_json(Path(tmp)/'0001/outcome.json')['state'],'failed_or_in_doubt')
    async def test_truncated_output_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            client=BudgetedText('test',tmp,max_calls=1,transport=lambda body:{'candidates':[{'finishReason':'MAX_TOKENS'}]})
            with self.assertRaises(ValueError):await client('one')
            self.assertEqual(client.calls,1)
