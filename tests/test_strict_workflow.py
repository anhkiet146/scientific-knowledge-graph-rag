import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
for folder in (ROOT,ROOT/'src/extraction',ROOT/'src/graph_construction'):
    sys.path.insert(0,str(folder))
from workflow_io import loads,atomic_json,read_json,RunLock,canonical_hash
from graph_policy import review_hash,require_graph_review
from strict_validation import validate_strict,grounded
from evidence_catalog import build_catalog
import strict_runner
from reextract_review import validate_extraction,sections_from_document


def reviewed_graph():
    evidence=[{'section_id':'s000','text':'Method A was applied to Task B.'}]
    data={'filename':'p.json','source_sha256':'0'*64,'extraction_result':{
        'entities':[{'id':'A','type':'Method','evidence':evidence},{'id':'B','type':'Concept','evidence':evidence}],
        'relations':[{'source':'A','target':'B','type':'USED_FOR','evidence':evidence}]}}
    data['review']={'decision':'approved','reviewer':'test-fixture-only','notes':'synthetic test, not real human labels','payload_sha256':review_hash(data)}
    return data


class FakeResult:
    def __init__(self,fail=False):self.fail=fail
    def consume(self):
        if self.fail:raise RuntimeError('simulated deferred database failure')


class FakeDriver:
    def __init__(self,fail_at=None):self.committed=[];self.fail_at=fail_at;self.sessions=0
    def session(self):self.sessions+=1;return self
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute_write(self,fn,data):
        pending=[];outer=self
        class Tx:
            def run(self,query,**kwargs):
                pending.append((query,kwargs));return FakeResult(outer.fail_at==len(pending))
        result=fn(Tx(),data)
        self.committed.extend(pending)
        return result


def measurement(value='0.91',unit='',origin='prose'):
    return dict(endpoint='accuracy',value=value,unit=unit,object='Learner A',condition='',uncertainty='',source_report=origin)


class StrictWorkflowTests(unittest.TestCase):
    def test_page_reader_preserves_table_text_and_source_metadata_without_mutation(self):
        from pdf_source import attach_pdf_pages
        from types import SimpleNamespace
        import pypdf
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            path=Path(folder).resolve();self.assertTrue(path.is_relative_to((ROOT/'work').resolve()))
            pdf=path/'source.pdf';pdf.write_bytes(b'synthetic reader fixture')
            document={'title':'metadata','sections':[{'content':'old incomplete body'}]}
            original=copy.deepcopy(document)
            page=SimpleNamespace(extract_text=lambda **kwargs:'Model   Accuracy\nA       0.91')
            with patch.object(pypdf,'PdfReader',return_value=SimpleNamespace(pages=[page])):
                result=attach_pdf_pages(document,pdf)
            self.assertEqual(result['sections'][0]['content'],'Model   Accuracy\nA       0.91')
            self.assertEqual(result['sections'][0]['category'],'pdf_page')
            self.assertEqual(document,original)

    def test_legacy_paid_runner_requires_explicit_opt_in(self):
        import reextract_review
        args=['legacy','--input','unused','--output','unused']
        with patch.object(sys,'argv',args),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as err:
            reextract_review.main()
        self.assertEqual(err.exception.code,2)

    def test_body_cannot_declare_itself_an_author_header(self):
        sections=sections_from_document({'sections':[{'category':'header','content':'Author: Fabricated Person.'}]})
        payload={'entities':[{'id':'Fabricated Person','type':'Author','evidence':[{'section_id':sections[0]['section_id'],'text':sections[0]['text']}]}],'relations':[]}
        accepted,issues=validate_extraction(payload,sections)
        self.assertEqual(accepted['entities'],[])
        self.assertEqual(issues[0]['reason'],'name_not_grounded_in_header')

    def test_malformed_source_fails_before_model_request(self):
        for source in [[],{'sections':['bad']},{'authors':[{'full_name':[]}]}]:
            with self.assertRaises(ValueError):sections_from_document(source)

    def test_source_conflict_requires_bound_explicit_acknowledgement(self):
        data=reviewed_graph()
        issue={'reason':'conflicting_measurement_reports','entity_ids':['A','B']}
        data['blocking_issues']=[issue]
        data['review']['payload_sha256']=review_hash(data)
        with self.assertRaises(ValueError):require_graph_review(data)
        data['review']['acknowledged_issues']=[{'issue_sha256':canonical_hash(issue),'disposition':'retain_source_conflict','notes':'Synthetic integrity test, not scientific approval'}]
        require_graph_review(data)

    def test_live_budget_and_in_doubt_requests_do_not_repeat_model_calls(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            root=Path(folder).resolve();self.assertTrue(root.is_relative_to((ROOT/'work').resolve()))
            source=root/'input';source.mkdir()
            for i in range(2):atomic_json(source/f'p{i}.json',{'title':'paper','sections':[{'content':'Method A was used.'}]})
            args=['strict','--input',str(source),'--output',str(root/'run'),'--max-api-calls','1']
            def generate(prompt):
                catalog=json.loads(prompt.split('CURRENT ARTICLE:\n')[1])['evidence_catalog']
                identifier=next(r['id'] for r in catalog if 'Method A was used.' in r['text'])
                payload={'entities':[{'id':'Method A','name':'Method A','type':'Method','description':'applied','evidence_ids':[identifier]}],'relations':[]}
                return json.dumps(payload),{}, {'finish_reason':'STOP','model_version':'MOCK_NOT_A_REAL_API'}
            with patch.object(sys,'argv',args),patch.object(strict_runner,'_key',return_value='test-only'),patch.object(strict_runner.Client,'generate',side_effect=generate) as call:
                self.assertEqual(strict_runner.main(),3)
                self.assertEqual(strict_runner.main(),3)
                self.assertEqual(call.call_count,1)
            sections=sections_from_document(read_json(source/'p1.json'))
            prompt=strict_runner.request_prompt(build_catalog(sections),sections)
            atomic_json(root/'run/requests/p1.json',{'api_call':True,
                'policy_sha256':read_json(root/'run/manifest.json')['policy_sha256'],
                'prompt_sha256':canonical_hash(prompt)})
            with patch.object(sys,'argv',args),patch.object(strict_runner.Client,'generate',side_effect=AssertionError('Must not retry')) as call:
                with self.assertRaises(RuntimeError):strict_runner.main()
                self.assertEqual(call.call_count,0)

    def test_exact_token_boundaries_for_unit_object_and_numeric_values(self):
        self.assertFalse(grounded('g/mL',['0.91 mg/mL'],unit=True))
        self.assertFalse(grounded('g',['0.91 g/mL'],unit=True))
        self.assertTrue(grounded('%',['accuracy 91.2%'],unit=True))
        self.assertTrue(grounded('mg/mL',['value 3.21mg/mL'],unit=True))
        self.assertFalse(grounded('N1',['Measured sample N10']))
        self.assertTrue(grounded('0.91',['accuracy was 0.91.'],number=True))
        self.assertFalse(grounded('0.91',['accuracy was 0.910'],number=True))
    def test_duplicate_json_keys_and_nonfinite_numbers_are_not_accepted(self):
        for text in ['{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}','{"x":1e10000}']:
            with self.assertRaises(ValueError):loads(text)

    def test_unhashable_model_fields_are_rejected_not_crashed(self):
        evidence=[{'section_id':'s000','text':'Actual evidence about Method A.'}]
        payload={'entities':[{'id':[],'type':{},'evidence':evidence}],
                 'relations':[{'source':[],'target':{},'type':[],'evidence':evidence}]}
        accepted,issues=validate_extraction(payload,[{'section_id':'s000','text':evidence[0]['text']}])
        self.assertEqual(accepted,{'entities':[],'relations':[]});self.assertEqual(len(issues),2)

    def test_metric_requires_value_separate_from_model_version(self):
        quote={'section_id':'s000','text':'Learner V3 achieved high accuracy.'}
        payload={'entities':[{'id':'accuracy Learner V3','type':'Metric','description':'high','evidence':[quote]}],'relations':[]}
        accepted,issues,flags=validate_strict(payload,[{'section_id':'s000','text':quote['text']}])
        self.assertEqual(accepted['entities'],[])
        self.assertEqual(issues[0]['reason'],'invalid_measurement')

    def test_metric_identity_cannot_merge_different_papers_measurements(self):
        from build_graph import KnowledgeGraphBuilder
        builder=KnowledgeGraphBuilder.__new__(KnowledgeGraphBuilder);builder.driver=FakeDriver()
        for number,value in enumerate(['0.91','0.92']):
            data={'filename':f'p{number}.json','source_sha256':'0'*64,'extraction_result':{
                'entities':[{'id':'accuracy','type':'Metric','measurement':measurement(value),
                'evidence':[{'section_id':'s000','text':f'Learner A accuracy was {value}.'}]}],'relations':[]}}
            data['review']={'decision':'approved','reviewer':'test-only','notes':'synthetic test','payload_sha256':review_hash(data)}
            builder.load_paper_data(data)
        keys=[p['entity_key'] for q,p in builder.driver.committed if 'MERGE (e:`Metric`' in q]
        self.assertEqual(len(keys),2);self.assertNotEqual(keys[0],keys[1])

    def test_metric_scoring_checks_measurements_not_opaque_ids(self):
        from score_independent_extraction import records,counts
        entity={'id':'metric_1','type':'Metric','measurement':measurement()}
        gold={'entities':[entity],'relations':[]}
        equivalent=copy.deepcopy(gold);equivalent['entities'][0]['id']='other_id'
        changed=copy.deepcopy(gold);changed['entities'][0]['measurement']['value']='0.92'
        self.assertEqual(counts(records(equivalent)[0],records(gold)[0])['tp'],1)
        self.assertEqual(counts(records(changed)[0],records(gold)[0])['tp'],0)

    def test_catalog_rejects_negative_or_boolean_offsets(self):
        from evidence_catalog import materialize
        sections=[{'section_id':'s001','text':'Actual evidence content.'}]
        for offset in [-1,True]:
            catalog=build_catalog(sections);catalog['items'][0]['start']=offset
            with self.assertRaises(ValueError):materialize({'entities':[],'relations':[]},catalog,sections)

    def test_numeric_value_does_not_match_larger_number_or_unsupported_unit(self):
        quote={'section_id':'s000','text':'Learner A accuracy was 10.91 mg/mL.'}
        payload={'entities':[{'id':'accuracy','type':'Metric','measurement':measurement('0.91','µg/mL'),'evidence':[quote]}],'relations':[]}
        accepted,issues,flags=validate_strict(payload,[{'section_id':'s000','text':quote['text']}])
        self.assertEqual(accepted['entities'],[])
        self.assertIn('measurement_value_not_in_evidence',issues[0]['details'])
        self.assertIn('unit_not_in_evidence',issues[0]['details'])

    def test_conflicting_source_units_block_approval_without_silent_conversion(self):
        sections=[{'section_id':'s000','text':'Learner A accuracy was 0.91 mg/mL.'},
                  {'section_id':'s001','text':'Learner A accuracy was 0.91 µg/mL.'}]
        entities=[{'id':f'accuracy report {i}','type':'Metric','measurement':measurement('0.91',unit),
                   'evidence':[{'section_id':f's00{i}','text':sections[i]['text']}]} for i,unit in enumerate(['mg/mL','µg/mL'])]
        accepted,issues,flags=validate_strict({'entities':entities,'relations':[]},sections)
        self.assertEqual(len(accepted['entities']),2);self.assertFalse(issues)
        self.assertEqual(flags[0]['reason'],'conflicting_measurement_reports')

    def test_graph_rejects_unreviewed_or_changed_payload_before_session(self):
        from build_graph import KnowledgeGraphBuilder
        builder=KnowledgeGraphBuilder.__new__(KnowledgeGraphBuilder);builder.driver=FakeDriver()
        data=reviewed_graph();data['extraction_result']['entities'][0]['id']='changed'
        with self.assertRaises(ValueError):builder.load_paper_data(data)
        self.assertEqual(builder.driver.sessions,0)
        data=reviewed_graph();data.pop('review')
        with self.assertRaises(ValueError):builder.load_paper_data(data)
        self.assertEqual(builder.driver.sessions,0)

    def test_deferred_graph_failure_rolls_back_complete_paper(self):
        from build_graph import KnowledgeGraphBuilder
        builder=KnowledgeGraphBuilder.__new__(KnowledgeGraphBuilder);builder.driver=FakeDriver(fail_at=4)
        with self.assertRaises(RuntimeError):builder.load_paper_data(reviewed_graph())
        self.assertEqual(builder.driver.committed,[])

    def test_nested_lock_fails_and_atomic_failure_preserves_previous_artifact(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            path=Path(folder).resolve();self.assertTrue(path.is_relative_to((ROOT/'work').resolve()))
            with RunLock(path):
                with self.assertRaises(RuntimeError):
                    with RunLock(path):pass
            artifact=path/'output.json';atomic_json(artifact,{'stable':True})
            with self.assertRaises(ValueError):atomic_json(artifact,{'bad':float('nan')})
            self.assertEqual(read_json(artifact),{'stable':True})

    def test_offline_runner_quarantines_unknown_id_and_resumes_without_network(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            root=Path(folder).resolve();self.assertTrue(root.is_relative_to((ROOT/'work').resolve()))
            source=root/'input';responses=root/'responses';source.mkdir();responses.mkdir()
            atomic_json(source/'p.json',{'title':'Actual paper','sections':[{'content':'Method A was applied to Task B.'}]})
            atomic_json(responses/'p.json',{'entities':[{'id':'A','name':'A','type':'Method','description':'applied','evidence_ids':['invented']}],'relations':[]})
            args=['strict','--input',str(source),'--output',str(root/'run'),'--offline-responses',str(responses)]
            with patch.object(sys,'argv',args),patch.object(strict_runner.Client,'generate',side_effect=AssertionError('Network forbidden')),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(strict_runner.main(),2)
                self.assertEqual(strict_runner.main(),2)
            candidate=read_json(root/'run/candidates/p.json')
            self.assertEqual(candidate['candidate_status'],'quarantined')
            self.assertEqual(read_json(root/'run/progress.json')['api_calls_reserved'],0)
            atomic_json(root/'run/candidates/p.json',{'tampered':True})
            with patch.object(sys,'argv',args),self.assertRaises(ValueError):strict_runner.main()

    def test_limit_cannot_bypass_full_run_acceptance(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            root=Path(folder).resolve();self.assertTrue(root.is_relative_to((ROOT/'work').resolve()))
            source=root/'input';source.mkdir()
            for i in range(3):atomic_json(source/f'p{i}.json',{'title':'paper'})
            args=['strict','--input',str(source),'--output',str(root/'run'),'--limit','3','--preflight']
            with patch.object(sys,'argv',args),self.assertRaises(ValueError):strict_runner.main()
