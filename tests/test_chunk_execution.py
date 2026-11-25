import copy
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from task_plan import plan
from chunk_contract import continuation,evaluate_task,evaluate_bounded_task
from chunk_merge import merge_tasks
from chunk_runner import run,prompt_for
from workflow_io import canonical_hash,read_json,atomic_json
from graph_policy import require_graph_review


class ChunkExecutionTests(unittest.TestCase):
    def setUp(self):
        self.document={'title':'Source title','raw_header':'Alice Doe, Example University.',
            'sections':[{'category':'pdf_page','page':1,'content':'\n'.join(
                f'Method number {i} was applied in the study.' for i in range(45))}]}
        self.planned=plan(self.document,20)
        from reextract_review import sections_from_document
        self.sections=sections_from_document(self.document)

    def output(self,task,entity=False):
        return {'entities':([{'id':'e1','name':'Source title','type':'Concept','description':'Source topic',
            'evidence_ids':[task['scope_ids'][0]]}] if entity else []),'relations':[],
            'completion':{'status':'complete','remaining_scope_ids':[]}}

    def test_continuation_requires_strict_progress_and_depth_limit(self):
        task={'task_id':'a','scope_ids':['x','y'],'context_ids':[]}
        for remaining in ([],['x','y'],['z'],['x','x']):
            with self.assertRaises(ValueError):continuation(task,remaining,3)
        child=continuation(task,['y'],3)
        self.assertEqual(child['context_ids'],['x'])
        with self.assertRaises(ValueError):continuation(child,['y'],3)
        with self.assertRaises(ValueError):continuation(task,['y'],0)

    def test_prompt_exposes_only_task_header_candidates_and_source_kinds(self):
        task=self.planned['tasks'][1]
        prompt=prompt_for(task,self.planned['catalog'],self.sections,12)
        envelope=json.loads(prompt.split('\nCURRENT TASK:\n')[1])
        entries={e['id']:e for e in envelope['evidence_catalog']}
        self.assertTrue(envelope['eligible_header_evidence_ids'])
        for eid in envelope['eligible_header_evidence_ids']:
            self.assertEqual(entries[eid]['kind'],'header')
            self.assertIn(eid,task['scope_ids']+task['context_ids'])
        self.assertEqual(set(entries),set(task['scope_ids']+task['context_ids']))

    def test_empty_chunk_allowed_but_unknown_evidence_rejected(self):
        task=self.planned['tasks'][0]
        _,issues,_,child=evaluate_task(self.output(task),task,self.planned['catalog'],self.sections)
        self.assertFalse(issues);self.assertIsNone(child)
        bad=self.output(task,True)
        bad['entities'][0]['evidence_ids']=[self.planned['tasks'][-1]['scope_ids'][0]]
        cleaned,issues,_,_=evaluate_task(bad,task,self.planned['catalog'],self.sections)
        self.assertTrue(issues);self.assertEqual(cleaned['entities'],[])

    def test_task_local_ids_do_not_conflate_different_entities(self):
        item=self.planned['catalog']['items'][0]
        from evidence_catalog import materialize
        resolved,_=materialize({'entities':[{'id':'x','name':'Source title','type':'Concept','description':'topic','evidence_ids':[item['id']]}],'relations':[]},self.planned['catalog'],self.sections)
        evidence=resolved['entities'][0]['evidence']
        def payload(name):
            return {'entities':[{'id':'e1','name':name,'type':'Concept','description':'Source topic','evidence':evidence}], 'relations':[]}
        merged,issues,_,provenance=merge_tasks({'a':payload('First concept'),'b':payload('Second concept')},self.sections,'a'*64)
        self.assertFalse(issues);self.assertEqual(len(merged['entities']),2)
        self.assertEqual(len(provenance),2)
        merged,issues,_,provenance=merge_tasks({'a':payload('First concept'),'b':payload('First concept')},self.sections,'a'*64)
        self.assertFalse(issues);self.assertEqual(len(merged['entities']),1)
        self.assertEqual(len(next(iter(provenance.values()))['task_local_ids']),2)

    def fixtures(self,base,empty=False):
        source=base/'input';source.mkdir();atomic_json(source/'paper.json',self.document)
        key=canonical_hash('paper.json')[:20];fixtures=base/'fixtures'/key;fixtures.mkdir(parents=True)
        for n,task in enumerate(self.planned['tasks']):
            atomic_json(fixtures/(task['task_id']+'.json'),{'text':json.dumps(self.output(task,not empty and n==0))})
        args=Namespace(input=source,output=base/'run',limit=2,max_api_calls=2,max_tasks=1,max_items=20,
            max_depth=3,max_metrics=12,requests_per_minute=4,offline_responses=base/'fixtures',
            extend_budget=False,preflight=False,keys_file=None)
        return args,key

    def test_offline_stop_resume_and_receipt_tamper(self):
        with tempfile.TemporaryDirectory() as tmp,patch('chunk_runner.Client',side_effect=AssertionError('No API allowed')):
            args,key=self.fixtures(Path(tmp))
            self.assertEqual(run(args),3)
            candidate=read_json(args.output/'papers'/(key+'.json'))
            self.assertEqual(candidate['candidate_status'],'incomplete')
            with self.assertRaisesRegex(ValueError,'coverage'):require_graph_review(candidate)
            first=args.output/'tasks'/key/'metadata'/'receipt.json';before=first.read_bytes()
            args.max_tasks=0;self.assertEqual(run(args),0)
            self.assertEqual(before,first.read_bytes())
            candidate=read_json(args.output/'papers'/(key+'.json'))
            self.assertTrue(candidate['execution_coverage']['complete'])
            self.assertEqual(candidate['candidate_status'],'pending_semantic_review')
            self.assertEqual(read_json(args.output/'progress.json')['reserved_call_slots'],0)
            with self.assertRaises(ValueError):require_graph_review(candidate)
            result=first.parent/'result.json';value=read_json(result);value['status']='tampered';atomic_json(result,value)
            with self.assertRaisesRegex(ValueError,'hash mismatch'):run(args)

    def test_empty_paper_is_quarantined(self):
        with tempfile.TemporaryDirectory() as tmp:
            args,key=self.fixtures(Path(tmp),empty=True);args.max_tasks=0
            self.assertEqual(run(args),2)
            candidate=read_json(args.output/'papers'/(key+'.json'))
            self.assertIn('empty_paper_extraction',[i['reason'] for i in candidate['validation_issues']])

    def test_budget_changes_require_explicit_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            args,_=self.fixtures(Path(tmp));args.preflight=True
            self.assertEqual(run(args),0);args.max_api_calls=3
            with self.assertRaisesRegex(ValueError,'extend-budget'):run(args)
            args.extend_budget=True;self.assertEqual(run(args),0)
            self.assertEqual(read_json(args.output/'budget.json')['history'],[{'from':2,'to':3}])

    def test_in_doubt_request_is_never_retried(self):
        with tempfile.TemporaryDirectory() as tmp,patch('chunk_runner.Client',side_effect=AssertionError('No retry')):
            args,key=self.fixtures(Path(tmp));args.preflight=True;run(args);args.preflight=False
            folder=args.output/'tasks'/key/'metadata';folder.mkdir(parents=True)
            atomic_json(folder/'request.json',{})
            with self.assertRaisesRegex(RuntimeError,'In-doubt'):run(args)

    def test_continuation_is_executed_and_included_in_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            args,key=self.fixtures(Path(tmp));args.max_tasks=0
            parent=self.planned['tasks'][1];remaining=parent['scope_ids'][10:]
            child=continuation(parent,remaining,3)
            payload=self.output(parent);payload['completion']={'status':'needs_continuation','remaining_scope_ids':remaining}
            atomic_json(args.offline_responses/key/(parent['task_id']+'.json'),{'text':json.dumps(payload)})
            atomic_json(args.offline_responses/key/(child['task_id']+'.json'),{'text':json.dumps(self.output(child))})
            self.assertEqual(run(args),0)
            coverage=read_json(args.output/'papers'/(key+'.json'))['execution_coverage']
            self.assertIn(child['task_id'],coverage['completed_tasks'])
            self.assertEqual(len(coverage['completed_tasks']),len(self.planned['tasks'])+1)
            self.assertEqual(run(args),0)

    def test_truncated_response_is_quarantined_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            args,key=self.fixtures(Path(tmp));args.max_tasks=0
            path=args.offline_responses/key/'metadata.json';value=read_json(path)
            value['finish_reason']='MAX_TOKENS';atomic_json(path,value)
            self.assertEqual(run(args),2)
            coverage=read_json(args.output/'papers'/(key+'.json'))['execution_coverage']
            self.assertFalse(coverage['complete']);self.assertEqual(coverage['failed_tasks'],['metadata'])

    def test_merge_remaps_relation_endpoints_by_task(self):
        evidence=[{'section_id':'s001','text':'Alice Doe is affiliated with Example University.'}]
        sections=[{'section_id':'s001','kind':'header','text':evidence[0]['text']}]
        def payload(author,institution):
            return {'entities':[{'id':author,'name':'Alice Doe','type':'Author','description':'Author','evidence':evidence},
                {'id':institution,'name':'Example University','type':'Institution','description':'Affiliation','evidence':evidence}],
                'relations':[{'source':author,'target':institution,'type':'AFFILIATED_WITH','evidence':evidence}]}
        merged,issues,_,_=merge_tasks({'a':payload('e1','e2'),'b':payload('e2','e1')},sections,'a'*64)
        self.assertFalse(issues);self.assertEqual(len(merged['relations']),1)
        names={e['id']:e['name'] for e in merged['entities']};edge=merged['relations'][0]
        self.assertEqual(names[edge['source']],'Alice Doe');self.assertEqual(names[edge['target']],'Example University')

    def test_metric_overrun_preserves_valid_records_but_requires_review(self):
        from evidence_catalog import build_catalog
        sections=[{'section_id':'s001','kind':'body','text':'Model A accuracy was 91% and Model A accuracy was 92%.'}]
        catalog=build_catalog(sections);eid=catalog['items'][0]['id']
        task={'task_id':'body','scope_ids':[eid],'context_ids':[]}
        payload={'entities':[{'id':'m'+v,'name':'accuracy','type':'Metric','description':'Measured accuracy',
            'evidence_ids':[eid],'measurement':{'endpoint':'accuracy','value':v,'unit':'%',
                'object':'Model A','condition':'','uncertainty':'','source_report':'prose'}} for v in ('91','92')],
            'relations':[],'completion':{'status':'complete','remaining_scope_ids':[]}}
        accepted,issues,_,child=evaluate_bounded_task(payload,task,catalog,sections,max_metrics=1)
        self.assertEqual(len(accepted['entities']),2)
        self.assertEqual([i['reason'] for i in issues],['metric_output_limit_exceeded'])
        self.assertIsNone(child)
