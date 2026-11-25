"""Exercise route/database methods with fakes; no service connections on import."""
import ast
import copy
from datetime import datetime
from pathlib import Path
import sys
from types import SimpleNamespace,ModuleType
from typing import Optional
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from test_strict_workflow import reviewed_graph


def function(path,name,namespace,cls=None):
    tree=ast.parse(path.read_text(encoding='utf-8'))
    nodes=tree.body if cls is None else next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls).body
    node=next(n for n in nodes if isinstance(n,ast.FunctionDef) and n.name==name)
    node.decorator_list=[]
    exec(compile(ast.Module(body=[node],type_ignores=[]),'isolated_contract_test','exec'),namespace)
    return namespace[name]


class ReviewApiContractTests(unittest.TestCase):
    def test_upload_sdk_does_not_silently_retry_paid_calls(self):
        from google.genai import types
        tree=ast.parse((ROOT/'src/api/web_backend.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.Assign)
                  and any(isinstance(t,ast.Name) and t.id=='gemini_client' for t in n.targets))
        constructor=Mock();namespace={'genai':SimpleNamespace(Client=constructor),'types':types,'GEMINI_API_KEY':'test-not-secret'}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'sdk_retry_contract','exec'),namespace)
        self.assertEqual(constructor.call_args.kwargs['http_options'].retry_options.attempts,1)

    def test_mongo_keeps_provenance_and_commit_claim_is_compare_and_set(self):
        namespace={'datetime':datetime}
        save=function(ROOT/'src/api/database_mongo.py','save_extraction_result',namespace,'MongoManager')
        collection=SimpleNamespace(replace_one=Mock())
        candidate=reviewed_graph()
        save(SimpleNamespace(extraction_results=collection),'f','title','abstract',[],[],candidate=candidate)
        stored=collection.replace_one.call_args.args[1]
        self.assertEqual(stored['candidate']['source_sha256'],candidate['source_sha256'])
        self.assertIn('review',stored['candidate'])
        claim=function(ROOT/'src/api/database_mongo.py','claim_graph_commit',{},'MongoManager')
        class Queue:
            status='extracted'
            def update_one(self,query,update):
                if query['status']!=self.status:return SimpleNamespace(modified_count=0)
                self.status=update['$set']['status'];return SimpleNamespace(modified_count=1)
        database=SimpleNamespace(upload_queue=Queue())
        self.assertTrue(claim(database,'f'));self.assertFalse(claim(database,'f'))

    def test_commit_requires_bound_review_and_does_not_approve_stored_candidate(self):
        class HTTPError(Exception):
            def __init__(self,status_code,detail):self.status_code=status_code;self.detail=detail
        original=reviewed_graph();review=original.pop('review')
        class DB:
            claimed=False
            def get_extraction_result(self,file_id):return {'candidate':original}
            def claim_graph_commit(self,file_id):
                if self.claimed:return False
                self.claimed=True;return True
            def update_queue_status(self,*args,**kwargs):pass
        db=DB();namespace={'copy':copy,'Optional':Optional,'GraphReviewRequest':SimpleNamespace,'HTTPException':HTTPError,
                           'db':db,'logger':SimpleNamespace(error=Mock())}
        commit=function(ROOT/'src/api/main.py','commit_to_neo4j',namespace)
        with self.assertRaises(HTTPError) as err:commit('f')
        self.assertEqual(err.exception.status_code,409);self.assertFalse(db.claimed)
        stale=SimpleNamespace(model_dump=lambda:{**review,'payload_sha256':'stale'})
        with self.assertRaises(HTTPError):commit('f',stale)
        self.assertFalse(db.claimed)
        backend=ModuleType('web_backend');backend.save_to_neo4j=Mock(return_value={'entities_saved':2,'relations_saved':1})
        request=SimpleNamespace(model_dump=lambda:review)
        with patch.dict(sys.modules,{'web_backend':backend}):
            self.assertEqual(commit('f',request)['status'],'committed')
            with self.assertRaises(HTTPError):commit('f',request)
        self.assertEqual(backend.save_to_neo4j.call_count,1)
        self.assertNotIn('review',original)
