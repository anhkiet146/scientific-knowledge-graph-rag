import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/retrieval'))
from paper_scope import PaperScope,ScopedIndex
from hybrid_retrieval import build_query_plan,rerank_candidates

class PaperScopeTests(unittest.TestCase):
    def test_source_title_keeps_named_study_method_relevant(self):
        query='Which analytical methods identify compounds from Salvia officinalis?'
        item={'entity_name':'NMR spectroscopy','entity_type':'Method','entity_desc':'Structural elucidation by nuclear magnetic resonance.',
              'source_papers':['Compounds from Salvia officinalis'],'source_count':1,'retrieval_score':5,'degree':0,'hop_distance':0,'connections':[]}
        ranked=rerank_candidates(query,build_query_plan(query,{'keywords':[query]}),[item],max_context=8)
        self.assertTrue(ranked)

    def test_named_species_selects_source_without_question_ids(self):
        scope=PaperScope({'a':'Chemical constituents of Salvia officinalis','b':'Surface area of coconut coir'})
        result=scope.select('Which methods determine compounds of Salvia officinalis?')
        self.assertEqual(result['allowed_papers'],['a'])

    def test_generic_query_does_not_force_a_paper(self):
        scope=PaperScope({'a':'Methods for chemical analysis','b':'Comparison of analytical methods'})
        self.assertIsNone(scope.select('Which analytical methods were used?')['allowed_papers'])

    def test_missing_named_subject_does_not_invent_scope(self):
        scope=PaperScope({'a':'Growth of rice'})
        self.assertIsNone(scope.select('Study of Unseenorganism example')['allowed_papers'])

    def test_single_rare_generic_word_does_not_force_scope(self):
        scope=PaperScope({'a':'Relationship between arbitrary variables'})
        self.assertIsNone(scope.select('What is the relationship?')['allowed_papers'])

    def test_rare_anchors_in_different_papers_do_not_form_false_scope(self):
        scope=PaperScope({'a':'Autonomous systems','b':'Technical methods','c':'Components design'})
        self.assertIsNone(scope.select('autonomous technical components')['allowed_papers'])

    def test_source_filter_searches_beyond_global_top_k(self):
        class Index:
            def search(self,q,k):return [(0,5),(1,4)][:k]
        index=ScopedIndex(Index(),['a','b'],{'a':[{'paper':'wrong'}],'b':[{'paper':'right'}]},['right'])
        self.assertEqual(index.search('q',1),[(1,4)])

    def test_empty_scoped_search_does_not_fall_back_to_other_paper(self):
        class Index:
            def search(self,q,k):return [(0,5)]
        index=ScopedIndex(Index(),['a'],{'a':[{'paper':'wrong'}]},['right'])
        self.assertEqual(index.search('q',1),[])
