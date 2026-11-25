import copy
from pathlib import Path
import sys
import unittest
import subprocess
import os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/retrieval'))
from hybrid_retrieval import rerank_candidates


class RerankAuditTests(unittest.TestCase):
    def test_bm25_replay_is_exact_across_hash_seeds(self):
        root=Path(__file__).resolve().parents[1]
        code="import sys,json;sys.path.insert(0,sys.argv[1]);from snapshot_benchmark import BM25Index;docs=['alpha beta beta gamma delta','alpha gamma epsilon epsilon zeta','beta delta eta theta iota kappa'];print(json.dumps(BM25Index(docs).search('alpha beta gamma delta epsilon zeta eta theta iota kappa',3)))"
        results=[]
        for seed in ('1','7','99'):
            result=subprocess.run([sys.executable,'-c',code,str(root/'src/evaluation')],env={**os.environ,'PYTHONHASHSEED':seed},capture_output=True,text=True,check=True,timeout=30)
            results.append(result.stdout)
        self.assertEqual(len(set(results)),1)
    def candidates(self):
        return [{'entity_name':'Model A','entity_type':'Method','entity_desc':'Model A detects leaves.',
            'source_papers':['Leaf study'],'connections':[],'retrieval_score':1.,'degree':2}]
    def test_trace_does_not_change_selection_or_mutate_input(self):
        candidates=self.candidates();before=copy.deepcopy(candidates)
        plan={'answer_type':'method','expected_labels':['method'],'entities':[],'search_terms':['Model A']}
        plain=rerank_candidates('Which method detects leaves?',plan,candidates)
        audit={};traced=rerank_candidates('Which method detects leaves?',plan,candidates,audit=audit)
        self.assertEqual(plain,traced);self.assertEqual(candidates,before)
        self.assertTrue(audit['stages']);self.assertEqual(audit['candidate_count'],1)
        audit['scored_candidates'][0]['ranking']['score']=-999
        self.assertNotEqual(traced[0]['ranking']['score'],-999)
    def test_wrong_type_empty_result_has_mechanical_reason(self):
        audit={};result=rerank_candidates('Who wrote it?',{'answer_type':'author','expected_labels':['author'],'entities':[]},self.candidates(),audit=audit)
        self.assertEqual(result,[])
        self.assertEqual(audit['termination'],'no_direct_evidence_for_expected_type')
        self.assertIn('unexpected_entity_type',audit['scored_candidates'][0]['base_direct_rejection_reasons'])
    def test_no_candidate_trace_and_invalid_audit(self):
        audit={};self.assertEqual(rerank_candidates('q',{},[],audit=audit),[])
        self.assertEqual(audit['termination'],'no_candidates')
        with self.assertRaises(ValueError):rerank_candidates('q',{},[],audit=[])
