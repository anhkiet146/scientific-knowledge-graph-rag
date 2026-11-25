import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/evaluation'))
from vector_preflight import dense_topk,bound_context


class VectorPreflightTests(unittest.TestCase):
    def test_actual_cosine_ranking_and_deterministic_ties(self):
        index=np.array([[1.,0.],[0.,1.],[1.,0.]])
        hits=dense_topk(index,np.array([1.,0.]),3)
        self.assertEqual([i for i,_ in hits],[0,2,1]);self.assertEqual(hits[0][1],1.)
    def test_wrong_dimension_nonfinite_or_unnormalized_data_rejected(self):
        for matrix,query in [(np.eye(2),[1.]),(np.eye(2),[float('nan'),0]),
            (np.array([[2.,0.]]),[1.,0.]),(np.eye(2),[0.,0.])]:
            with self.assertRaises(ValueError):dense_topk(matrix,query,2)
    def test_context_boundary_preserves_original_source_not_index_text(self):
        chunks=[{'paper_id':'a','text':'original source alpha'},{'paper_id':'b','text':'original source beta'}]
        rows,size=bound_context(chunks,[(1,.9),(0,.8)],12000)
        self.assertEqual(rows[0]['text'],chunks[1]['text']);self.assertEqual(rows[0]['chunk_id'],1)
        self.assertNotIn('retrieval_score',rows[0]);self.assertGreater(size,0)
    def test_too_small_context_budget_has_no_partial_fabricated_passage(self):
        self.assertEqual(bound_context([{'text':'original source'}],[(0,1.)],1),([],0))
