import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT/'src/normalization', ROOT/'src/evaluation', ROOT/'src/graph_construction'):
    sys.path.insert(0,str(directory))
from normalize_entities import normalize_folder, normalize_surface, source_surface
from judge_existing_results import apply_judgment
from run_metadata import save_run_metadata
import run_baseline_comparison as baselines


class ManuscriptAlignmentTests(unittest.TestCase):
    def test_http_questions_do_not_reuse_dialogue_history(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return b'{}'
        with patch.object(baselines.urllib.request,'urlopen',return_value=Response()) as call:
            baselines.ask_kg_via_http('http://localhost/ask','same question')
            baselines.ask_kg_via_http('http://localhost/ask','same question')
        sessions=[json.loads(args.args[0].data)['session_id'] for args in call.call_args_list]
        self.assertNotEqual(*sessions)

    def test_graph_import_does_not_merge_paper_scoped_authors(self):
        from build_graph import _write_paper
        class Result:
            def consume(self):pass
        class Transaction:
            def __init__(self):self.author_keys=[]
            def run(self,query,**parameters):
                if query.startswith('MERGE (e:`Author`'):
                    self.author_keys.append(parameters['entity_key'])
                return Result()
        tx=Transaction()
        for paper in ['one.json','two.json']:
            _write_paper(tx,{'filename':paper,'source_sha256':'synthetic','review':{},
                'extraction_result':{'entities':[{'id':'a','name':'Alice Doe','type':'Author',
                    'identity_scope':'paper','evidence':[]}],'relations':[]}})
        self.assertEqual(len(tx.author_keys),2)
        self.assertNotEqual(*tx.author_keys)

    def test_source_rule_keeps_operators_units_case_and_versions(self):
        self.assertEqual(normalize_surface('P > 0.05'), normalize_surface('P < 0.05'))
        for a,b in [('P > 0.05','P < 0.05'), ('P <= 0.05','P < 0.05'),
                    ('10 mg','10 g'), ('Minitab 13','Minitab 16'), ('Co','CO')]:
            self.assertNotEqual(source_surface(a),source_surface(b))

    def test_source_normalization_keeps_ids_and_paper_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'input';source.mkdir();out=root/'out'
            paper={'extraction_result':{'entities':[
                {'id':'a','name':'Alice Doe','type':'Author'},
                {'id':'m','name':'P > 0.05','type':'Metric'},
                {'id':'c','name':'Co','type':'Concept'}],
                'relations':[{'source':'a','target':'m','type':'RELATED_TO'}]}}
            for name in ['one.json','two.json']:(source/name).write_text(json.dumps(paper),encoding='utf-8')
            before=(source/'one.json').read_bytes()
            report=normalize_folder(source,out,'source_preserving')
            result=json.loads((out/'one.json').read_text())['extraction_result']
            self.assertEqual([e['id'] for e in result['entities']],['a','m','c'])
            self.assertEqual(result['relations'],paper['extraction_result']['relations'])
            self.assertEqual([e['identity_scope'] for e in result['entities']],['paper','paper','corpus'])
            self.assertEqual(report['canonical_typed_names'],5)
            self.assertEqual(before,(source/'one.json').read_bytes())
            with self.assertRaises(FileExistsError):normalize_folder(source,out,'source_preserving')

    def test_failed_judge_cannot_inherit_success_metadata(self):
        row={'judge_model':'old-model','judge_model_used':'old-model','judge_response_id':'old-id'}
        apply_judgment(row,{'faithfulness':None,'notes':'quota'},'gpt-5.5','openai')
        self.assertIsNone(row['judge_model'])
        self.assertNotIn('judge_response_id',row)
        self.assertEqual(row['judge_model_requested'],'gpt-5.5')

    def test_judge_records_actual_model_separately_from_requested(self):
        row={};apply_judgment(row,{'judge_model_used':'returned-snapshot','faithfulness':.5},'gpt-5.5','openai')
        self.assertEqual(row['judge_model'],'returned-snapshot')
        self.assertEqual(row['scoring_method'],'llm_rubric_ragas_informed')

    def test_index_metadata_retains_first_measurement_and_rejects_changed_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);corpus=root/'corpus';corpus.mkdir()
            q=root/'questions.py';q.write_text('questions=[]',encoding='utf-8')
            article=corpus/'one.json';article.write_text('{}',encoding='utf-8')
            path=root/'metadata.json';kwargs=dict(question_file=q,corpus_dir=corpus,config={'embedding':'configured-model'})
            first=save_run_metadata(path,**kwargs,index_preparation={'vector':{'seconds':2,'cache_hit':False}})
            second=save_run_metadata(path,**kwargs,index_preparation={'vector':{'seconds':.1,'cache_hit':True}})
            self.assertEqual(second['runtime'],first['runtime'])
            self.assertEqual(second['index_preparation'],first['index_preparation'])
            self.assertTrue(second['continuations'][0]['index_preparation']['vector']['cache_hit'])
            self.assertIsNone(second['runtime']['neo4j_server_version'])
            article.write_text('{"changed":true}',encoding='utf-8');before=path.read_bytes()
            with self.assertRaises(ValueError):save_run_metadata(path,**kwargs,index_preparation={})
            self.assertEqual(path.read_bytes(),before)


if __name__=='__main__':unittest.main()
