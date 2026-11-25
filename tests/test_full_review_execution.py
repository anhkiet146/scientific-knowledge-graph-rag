import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src/evaluation')]
from budgeted_gemini_text import BudgetedText
from run_fair_qa_batch import execute
from workflow_io import atomic_json,file_hash
from workflow_io import canonical_hash,read_json
from resumable_study import run_study
from claim_verification import REFUSAL


class FullReviewExecutionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)
        self.settings={'question_count':45,'repeats':5,
            'context_methods':['bm25','vector','kg','lightrag','kg_no_expansion','kg_raw','kg_no_semantic','kg_no_relation'],
            'generation':{'model':'gemini-2.5-flash','temperature':0,'thinking_budget':0,
                'max_output_tokens':1024,'references_in_prompt':False,'automatic_retry':False,
                'key_rotation':False,'shared_prompt_implementation_sha256':file_hash(ROOT/'src/evaluation/snapshot_benchmark.py')}}
        self.protocol=self.path/'protocol.json';self.bundles=self.path/'bundles.json'
        atomic_json(self.bundles,{})

    async def invoke(self,**kwargs):
        atomic_json(self.protocol,self.settings)
        return await execute(self.protocol,self.bundles,self.path/'out',list,**kwargs)

    async def test_full_scope_supports_complete_budget_without_sending_requests(self):
        client=BudgetedText('synthetic',self.path/'journal',max_calls=2025,scope='review_generation')
        self.assertEqual(client.maximum,2025)
        self.assertEqual(client.calls,0)
        with self.assertRaises(ValueError):
            BudgetedText('synthetic',self.path/'too_large',max_calls=2026,scope='review_generation')

    async def test_full_flag_selects_full_scope_and_five_repeats(self):
        study=AsyncMock(return_value={'state':'stub'})
        with patch('run_fair_qa_batch.verified_contexts',return_value=({'status':'ready_for_controlled_generation'},[])),\
             patch('run_fair_qa_batch._key',return_value='synthetic'),\
             patch('run_fair_qa_batch.BudgetedText') as provider,\
             patch('run_fair_qa_batch.run_study',study):
            await self.invoke(live=True,full_run=True,max_calls=2025)
        self.assertEqual(provider.call_args.kwargs['scope'],'review_generation')
        self.assertEqual(provider.call_args.kwargs['max_calls'],2025)
        self.assertEqual(study.call_args.kwargs['repeats'],5)

    async def test_pilot_does_not_silently_acquire_full_budget(self):
        with patch('run_fair_qa_batch.verified_contexts',return_value=({'status':'ready_for_controlled_generation'},[])),\
             patch('run_fair_qa_batch._key',side_effect=AssertionError('Must reject before credentials')):
            with self.assertRaises(ValueError):await self.invoke(live=True,max_calls=17)

    async def test_full_flag_requires_all_questions_and_repeats(self):
        self.settings['repeats']=1
        with patch('run_fair_qa_batch.verified_contexts',return_value=({'status':'ready_for_controlled_generation'},[])),\
             patch('run_fair_qa_batch._key',side_effect=AssertionError('Must reject before credentials')):
            with self.assertRaises(ValueError):await self.invoke(live=True,full_run=True,max_calls=2025)

    async def test_full_flag_never_overrides_fairness_gate(self):
        with patch('run_fair_qa_batch.verified_contexts',return_value=({'status':'blocked','issues':['missing full corpus']},[])),\
             patch('run_fair_qa_batch._key',side_effect=AssertionError('Must not access credentials')),\
             patch('run_fair_qa_batch.BudgetedText') as provider:
            result=await self.invoke(live=True,full_run=True,max_calls=2025)
        self.assertEqual(result['status'],'blocked')
        provider.assert_not_called()

    def contexts(self):
        context=[{'text':'The change was +70 percent.'}]
        text=json.dumps(context)
        return [dict(question_id=1,method=method,question='What was the change?',context=context,
                     context_json=text,context_sha256=canonical_hash(text),context_tokens=12)
                for method in ['kg','kg_verified']]

    async def test_full_study_applies_selected_numeric_guard_and_binds_resume(self):
        draft='The change was -70 percent.'
        verdict={'claims':[{'text':draft,'quote':'The change was +70 percent.',
                            'context_index':0,'supported':True,'atomic':True}]}
        calls=[]
        async def provider(prompt,**kwargs):
            calls.append(prompt)
            return json.dumps(verdict) if kwargs.get('json_mode') else draft
        target=self.path/'numeric_study'
        result=await run_study(self.contexts(),target,provider,max_calls=2,repeats=1,
                               base_methods=['kg'],verification_policy='content_numeric')
        self.assertEqual(result['complete_records'],2)
        verified=read_json(target/'jobs/q1_r1_kg_verified/result.json')
        self.assertEqual(verified['answer'],REFUSAL)
        self.assertIn('numeric_token_or_sign_not_in_quote',verified['claim_audit'][0]['reasons'])
        with self.assertRaisesRegex(ValueError,'Resume contract changed'):
            await run_study(self.contexts(),target,provider,max_calls=2,repeats=1,
                            base_methods=['kg'],verification_policy='v2')
        self.assertEqual(len(calls),2)

    async def test_unknown_verifier_rejected_before_creating_study(self):
        target=self.path/'unknown_study'
        with self.assertRaises(ValueError):
            await run_study(self.contexts(),target,verification_policy='unknown')
        self.assertFalse(target.exists())


if __name__=='__main__':unittest.main()
