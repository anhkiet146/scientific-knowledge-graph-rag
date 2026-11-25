from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src/retrieval'),str(ROOT/'src/evaluation')]
from compare_normalization_retrieval import select_scope
from paper_scope import PaperScope,ScopedIndex
from snapshot_benchmark import BM25Index


class WholeCorpusAblationTests(unittest.TestCase):
    def test_whole_corpus_does_not_call_title_selector(self):
        scoper=Mock();scoper.select.side_effect=AssertionError('Title filter must not run')
        self.assertIsNone(select_scope(scoper,'uniconazole mango','whole_corpus')['allowed_papers'])
        scoper.select.assert_not_called()

    def test_lexical_title_anchor_cannot_hide_second_paper_in_whole_corpus(self):
        scoper=PaperScope({'a.json':'Uniconazole mango flowering','b.json':'Mango cultivation'})
        query='uniconazole mango flowering'
        keys=['a','b'];groups={'a':[{'paper':'a.json'}],'b':[{'paper':'b.json'}]}
        index=BM25Index(['uniconazole mango flowering','mango flowering'])
        scoped=select_scope(scoper,query,'title_scoped')
        self.assertEqual(scoped['allowed_papers'],['a.json'])
        self.assertEqual([i for i,_ in ScopedIndex(index,keys,groups,scoped['allowed_papers']).search(query,2)],[0])
        whole=select_scope(scoper,query,'whole_corpus')
        selected=ScopedIndex(index,keys,groups,whole['allowed_papers']) if whole['allowed_papers'] is not None else index
        self.assertEqual({i for i,_ in selected.search(query,2)},{0,1})

    def test_unknown_scope_rejected(self):
        with self.assertRaises(ValueError):select_scope(None,'query','guess')


if __name__=='__main__':unittest.main()
