import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src/evaluation')]
from audit_fair_comparison import verified_contexts
from run_fair_qa_batch import execute
from resumable_study import run_study
from workflow_io import atomic_json,file_hash,canonical_hash


class ActualArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'contexts.jsonl'
        text='[{"text":"source"}]'
        self.rows=[{'question_id':i,'method':'bm25','question':f'Q{i}','shared_query':f'R{i}',
            'context':json.loads(text),'context_json':text,'context_sha256':canonical_hash(text),'context_tokens':len(text)} for i in range(1,46)]
        self.protocol={'context_methods':['bm25'],'shared_dense_methods':[],
            'dense_conditions':{'threads':4},'shared_inputs':{'corpus_sha256':'source',
            'question_sha256':canonical_hash([(r['question_id'],r['question']) for r in self.rows]),
            'query_sha256':canonical_hash([(r['question_id'],r['shared_query']) for r in self.rows]),
            'scope_policy':'whole_corpus','context_limit_tokens':2000}}
        self.bundle={'state':'contexts_frozen',**self.protocol['shared_inputs'],'questions':45,'context_records':45}
        atomic_json(self.root/'manifest.json',{'corpus_sha256':'source'})
        atomic_json(self.root/'runtime.json',{'device':'cpu','torch_threads':4,'thread_limit':4,
            'thread_pools':[{'num_threads':4}],'thread_pools_after':[{'num_threads':4}],
            'platform':'test','machine':'test','processor':'test','logical_cpus':8})
        self.bundle.update(context_artifact=str(self.path),artifact_manifest=str(self.root/'manifest.json'),
            artifact_manifest_sha256=file_hash(self.root/'manifest.json'),runtime_artifact=str(self.root/'runtime.json'),
            runtime_artifact_sha256=file_hash(self.root/'runtime.json'))
        self.save()

    def save(self):
        self.path.write_text(''.join(json.dumps(r)+'\n' for r in self.rows),encoding='utf-8')
        self.bundle['context_artifact_sha256']=file_hash(self.path)
        atomic_json(self.root/'manifest.json',{'corpus_sha256':'source','contexts_sha256':file_hash(self.path),
                                              'runtime_sha256':file_hash(self.root/'runtime.json')})
        self.bundle['artifact_manifest_sha256']=file_hash(self.root/'manifest.json')

    def result(self):return verified_contexts(self.protocol,{'bm25':self.bundle},list)[0]

    def test_actual_artifacts_can_pass(self):
        self.assertEqual(self.result()['status'],'ready_for_controlled_generation')

    def test_claimed_token_count_does_not_override_actual_text(self):
        self.rows[0]['context_tokens']=1;self.save()
        self.assertEqual(self.result()['status'],'blocked')

    def test_actual_scope_cannot_be_hidden_by_metadata(self):
        self.rows[0]['paper_scope']={'allowed_papers':['only-one']};self.save()
        self.assertEqual(self.result()['status'],'blocked')

    def test_cpu_receipt_is_checked(self):
        p=self.root/'runtime.json';data=json.loads(p.read_text());data['thread_pools'][0]['num_threads']=16
        atomic_json(p,data);self.bundle['runtime_artifact_sha256']=file_hash(p)
        self.save()
        self.assertEqual(self.result()['status'],'blocked')

    def test_blocked_batch_never_reads_credentials(self):
        self.protocol['generation']={'model':'gemini-2.5-flash','temperature':0,'thinking_budget':0,'max_output_tokens':1024,
            'references_in_prompt':False,'automatic_retry':False,'key_rotation':False,
            'shared_prompt_implementation_sha256':file_hash(ROOT/'src/evaluation/snapshot_benchmark.py')}
        atomic_json(self.root/'protocol.json',self.protocol);atomic_json(self.root/'bundles.json',{})
        with patch('run_fair_qa_batch._key',side_effect=AssertionError('No secret read')),patch('run_fair_qa_batch.BudgetedText') as provider:
            result=asyncio.run(execute(self.root/'protocol.json',self.root/'bundles.json',self.root/'output',list,live=True,max_calls=1))
            provider.assert_not_called()
        self.assertEqual(result['status'],'blocked')

    def test_empty_contexts_abstain_identically_without_provider(self):
        rows=[{'question_id':1,'method':m,'question':'Question','context':[],
            'context_json':'[]','context_sha256':canonical_hash('[]'),'context_tokens':2} for m in ['kg','lightrag','kg_verified']]
        async def forbidden(*args,**kwargs):raise AssertionError('Empty contexts must not call provider')
        result=asyncio.run(run_study(rows,self.root/'study',forbidden,max_calls=0,repeats=1,base_methods=['kg','lightrag']))
        self.assertEqual(result['new_provider_attempts'],0)
        self.assertEqual(result['complete_records'],3)
        self.assertEqual(result['expected_records'],3)
