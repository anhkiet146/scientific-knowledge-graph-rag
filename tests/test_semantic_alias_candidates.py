import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from semantic_alias_candidates import candidate_pairs

class SemanticCandidateTests(unittest.TestCase):
    def test_nearby_names_never_cross_types_or_repeat_pairs(self):
        rows=[{'type':'Method','name':'Technique A'},{'type':'Method','name':'Technique B'},{'type':'Concept','name':'Technique C'}]
        pairs=candidate_pairs(rows,[[1,0],[1,0],[1,0]])
        self.assertEqual([(a,b) for a,b,_ in pairs],[(0,1)])

    def test_exact_surface_variants_are_not_semantic_candidates(self):
        rows=[{'type':'Method','name':' BERT '},{'type':'Method','name':'bert'}]
        self.assertEqual(candidate_pairs(rows,[[1,0],[1,0]]),[])

    def test_nonfinite_or_nonunit_embeddings_rejected(self):
        with self.assertRaises(ValueError):candidate_pairs([{'type':'Method','name':'A'}],[[2,0]])
        with self.assertRaises(ValueError):candidate_pairs([{'type':'Method','name':'A'}],[[float('nan'),0]])
