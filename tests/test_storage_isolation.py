import ast
from pathlib import Path
import os
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,MagicMock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/retrieval'))
from graph_connection import graph_session,selected_database


def mongo_method(name):
    tree=ast.parse((ROOT/'src/api/database_mongo.py').read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='MongoManager')
    node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
    return node


class StorageIsolationTests(unittest.TestCase):
    def test_explicit_database_routed_and_default_preserved(self):
        driver=Mock()
        with patch.dict(os.environ,{'NEO4J_DATABASE':'review482'}):graph_session(driver)
        driver.session.assert_called_once_with(database='review482')
        driver.reset_mock()
        with patch.dict(os.environ,{},clear=True):graph_session(driver)
        driver.session.assert_called_once_with()

    def test_system_or_invalid_database_rejected_before_session(self):
        driver=Mock()
        for value in ['system','','bad database','bad/name']:
            with patch.dict(os.environ,{'NEO4J_DATABASE':value}):
                with self.assertRaises(ValueError):graph_session(driver)
        driver.session.assert_not_called()

    def test_mongo_uses_isolated_target_before_indexes(self):
        class DB:
            def __getitem__(self,key):return key
        client=Mock();client.__getitem__=Mock(return_value=DB())
        target=SimpleNamespace(_connect=Mock(return_value=client),_ensure_indexes=Mock())
        namespace={'os':os}
        exec(compile(ast.Module(body=[mongo_method('__init__')],type_ignores=[]),'mongo_init','exec'),namespace)
        with patch.dict(os.environ,{'MONGODB_URI':'mongodb://127.0.0.1:27018','MONGODB_DATABASE':'review482'}):
            namespace['__init__'](target)
        self.assertEqual(target.uri,'mongodb://127.0.0.1:27018')
        client.__getitem__.assert_called_once_with('review482')
        target._ensure_indexes.assert_called_once()

    def test_mongo_does_not_return_an_unverified_client(self):
        namespace={'MongoClient':Mock(side_effect=ConnectionError('private URI')),
            'ConnectionFailure':ConnectionError,'ServerSelectionTimeoutError':TimeoutError,
            'logger':Mock(),'time':SimpleNamespace(sleep=Mock())}
        exec(compile(ast.Module(body=[mongo_method('_connect')],type_ignores=[]),'mongo_connect','exec'),namespace)
        with self.assertRaisesRegex(RuntimeError,'backend startup stopped'):
            namespace['_connect'](SimpleNamespace(uri='private URI'),1)
        self.assertNotIn('private URI',str(namespace['logger'].mock_calls))

    def test_fulltext_readiness_is_scoped_to_database_and_driver(self):
        import hybrid_retrieval as hybrid
        driver=MagicMock();session=driver.session.return_value.__enter__.return_value
        session.run.return_value.single.return_value={'count':1}
        hybrid._index_ready.clear()
        with patch.dict(os.environ,{'NEO4J_DATABASE':'review482'}):
            self.assertTrue(hybrid.ensure_fulltext_index(driver))
            self.assertTrue(hybrid.ensure_fulltext_index(driver))
        self.assertEqual(driver.session.call_count,1)
        with patch.dict(os.environ,{'NEO4J_DATABASE':'review_other'}):
            self.assertTrue(hybrid.ensure_fulltext_index(driver))
        self.assertEqual(driver.session.call_count,2)
        hybrid._index_ready.clear()


if __name__=='__main__':unittest.main()
