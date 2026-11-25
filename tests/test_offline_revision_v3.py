import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/evaluation'),str(ROOT/'src/extraction'),str(ROOT/'src/normalization')]
from workflow_io import canonical_hash,read_json,atomic_json
from evidence_ledger import build_ledger
from resumable_study import run_study,BASE_METHODS
from snapshot_benchmark import SnapshotGraph
from context_budget import evidence_units


def contexts():
    context=[{'text':'Phan Van Ut'}];text=json.dumps(context)
    return [{'question_id':1,'method':m,'question':'Who?','context':context,'context_json':text,'context_sha256':canonical_hash(text),'context_tokens':10}
            for m in (*BASE_METHODS,'kg_verified')]


class OfflineRevisionTests(unittest.TestCase):
    def test_preserved_graph_indexes_later_description_and_scopes_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            for index,desc in enumerate(['Initial description','uniquesecondsource']):
                (p/f'{index}.json').write_text(json.dumps({'paper_title':str(index),'entities':[
                    {'id':'BERT','type':'Method','description':desc}], 'relations':[]}),encoding='utf-8')
            graph=SnapshotGraph(p,preserve_evidence=True)
            candidates=graph.retrieve('uniquesecondsource',hops=0)
            self.assertTrue(candidates)
            units=evidence_units(candidates)
            self.assertEqual({u['source_file'] for u in units},{'0.json','1.json'})
            self.assertEqual({u['entity']['description'] for u in units},{'Initial description','uniquesecondsource'})

    def test_ledger_preserves_different_descriptions_and_unresolved_relations(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            for n,description in enumerate(['First fact','Different fact']):
                (p/f'{n}.json').write_text(json.dumps({'entities':[{'id':'BERT','type':'Method','description':description}],
                    'relations':[{'source':'BERT','target':'missing','type':'USED_FOR'}]}),encoding='utf-8')
            nodes,edges,audit=build_ledger(p)
            self.assertEqual(len(nodes),1);self.assertEqual(len(nodes[0]['occurrences']),2)
            self.assertEqual(audit['different_description_occurrences_hidden_by_legacy_first_description'],1)
            self.assertEqual(len(edges),2);self.assertTrue(all(r['state']=='unresolved_preserved' for r in edges))

    def test_resume_does_not_call_completed_jobs_and_rejects_changed_inputs(self):
        async def scenario(output):
            calls=[]
            async def provider(prompt,**kwargs):
                calls.append(prompt)
                return '{"claims":[]}' if kwargs['json_mode'] else 'Phan Van Ut'
            first=await run_study(contexts(),output,provider,3,1)
            self.assertEqual(first['new_provider_attempts'],3)
            second=await run_study(contexts(),output,provider,5,1)
            self.assertEqual(second['complete_records'],8);self.assertEqual(len(calls),8)
            third=await run_study(contexts(),output,provider,8,1)
            self.assertEqual(third['new_provider_attempts'],0);self.assertEqual(len(calls),8)
            # Crash after response persistence but before result persistence:
            # restore the result offline, never send its request again.
            next((output/'jobs').glob('*/result.json')).unlink()
            recovered=await run_study(contexts(),output,provider,8,1)
            self.assertEqual(recovered['complete_records'],8);self.assertEqual(len(calls),8)
            changed=contexts();changed[0]['question']='Changed'
            with self.assertRaises(ValueError):await run_study(changed,output,provider,8,1)
        with tempfile.TemporaryDirectory() as tmp:asyncio.run(scenario(Path(tmp)))

    def test_in_doubt_failure_not_retried(self):
        async def scenario(output):
            calls=[]
            async def fail(*args,**kwargs):calls.append(1);raise RuntimeError('unknown')
            self.assertEqual((await run_study(contexts(),output,fail,8,1))['state'],'provider_failure_or_in_doubt')
            self.assertEqual((await run_study(contexts(),output,fail,8,1))['state'],'in_doubt_request_no_automatic_retry')
            self.assertEqual(len(calls),1)
        with tempfile.TemporaryDirectory() as tmp:asyncio.run(scenario(Path(tmp)))
