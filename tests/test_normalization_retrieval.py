import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from compare_normalization_retrieval import expand

class Seeds:
    def search(self,query,k):return [(0,3.0)]

class RetrievalTests(unittest.TestCase):
    def test_new_edge_expands_reachable_evidence(self):
        keys=['a','b','c']
        before=expand(keys,Seeds(),{'a':set(),'b':set(),'c':set()},'query')
        after=expand(keys,Seeds(),{'a':{'b'},'b':{'a','c'},'c':{'b'}},'query')
        self.assertEqual(set(before),{'a'});self.assertEqual(set(after),{'a','b','c'})
        self.assertEqual(after['c'][0],2)

    def test_hop_limit_and_cycle_are_bounded(self):
        adj={'a':{'b'},'b':{'a','c'},'c':{'b','d'},'d':{'c'}}
        result=expand(['a','b','c','d'],Seeds(),adj,'q',hops=1)
        self.assertEqual(set(result),{'a','b'})

    def test_neighbor_order_deterministic(self):
        keys=['a','b','c'];adj={'a':{'c','b'},'b':{'a'},'c':{'a'}}
        self.assertEqual(list(expand(keys,Seeds(),adj,'q')),['a','b','c'])
