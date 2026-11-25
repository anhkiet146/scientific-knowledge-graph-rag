from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/evaluation'))
from fair_runtime import light_rag_parameters


class FairCachePolicyTests(unittest.TestCase):
    def protocol(self):return {'dense_conditions':{'backend':'nano-vectordb==0.0.4.3','metric':'cosine',
        'dimension':384,'device':'cpu','normalize':True,'threshold':-1.0}}

    def test_query_cache_disabled_without_disabling_index_resume(self):
        with patch('fair_runtime.importlib.metadata.version',side_effect=lambda name:'0.0.4.3' if name=='nano-vectordb' else '1.5.7'):
            params=light_rag_parameters(self.protocol())
        self.assertFalse(params['enable_llm_cache'])
        self.assertFalse(params['embedding_cache_config']['enabled'])
        self.assertFalse(params['embedding_cache_config']['use_llm_check'])
        self.assertTrue(params['enable_llm_cache_for_entity_extract'])

    def test_nonmatching_backend_rejected(self):
        settings=self.protocol();settings['dense_conditions']['backend']='different'
        with self.assertRaises(ValueError):light_rag_parameters(settings)
