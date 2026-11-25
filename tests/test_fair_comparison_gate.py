import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_fair_comparison import audit


class FairComparisonTests(unittest.TestCase):
    def setUp(self):
        self.protocol={'context_methods':['bm25','vector','kg','lightrag'],
            'shared_inputs':{'corpus_sha256':'488','query_sha256':'same','scope_policy':'whole_corpus','context_limit_tokens':2000},
            'shared_dense_methods':['vector','lightrag'],'dense_conditions':{'backend':'same','model':'same'},
            'released_sota':'LightRAG 1.5.7'}
        self.bundles={m:{'state':'contexts_frozen',**self.protocol['shared_inputs'],
            'questions':45,'context_records':45,'dense':{'backend':'same','model':'same'},
            'released_implementation':'LightRAG 1.5.7'} for m in self.protocol['context_methods']}

    def test_matching_conditions_are_only_generation_readiness(self):
        result=audit(self.protocol,self.bundles)
        self.assertEqual(result['status'],'ready_for_controlled_generation')
        self.assertFalse(result['quality_comparison_complete'])

    def test_corpus_scope_and_budget_mismatch_block(self):
        for field,value in [('corpus_sha256','482'),('scope_policy','title_scoped'),('context_limit_tokens',12000)]:
            bundles=copy.deepcopy(self.bundles);bundles['kg'][field]=value
            result=audit(self.protocol,bundles)
            self.assertEqual(result['status'],'blocked')
            self.assertIn(field,[i.get('field') for i in result['issues']])

    def test_different_dense_store_cannot_pass_latency_prerequisite(self):
        self.bundles['vector']['dense']['backend']='different'
        self.assertEqual(audit(self.protocol,self.bundles)['status'],'blocked')

    def test_missing_sota_blocks(self):
        del self.bundles['lightrag']
        self.assertEqual(audit(self.protocol,self.bundles)['status'],'blocked')

    def test_partial_grid_blocks(self):
        self.bundles['kg']['context_records']=44
        self.assertEqual(audit(self.protocol,self.bundles)['status'],'blocked')

    def test_online_cache_difference_blocks(self):
        self.protocol['cache_policy']={'online_llm_cache':False}
        for row in self.bundles.values():row['cache_policy']={'online_llm_cache':False}
        self.bundles['lightrag']['cache_policy']['online_llm_cache']=True
        result=audit(self.protocol,self.bundles)
        self.assertIn('cache_policy_mismatch',[i['reason'] for i in result['issues']])
