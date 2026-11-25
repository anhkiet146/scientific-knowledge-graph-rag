import copy
import io
import urllib.error
from unittest.mock import patch
import json
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
for folder in ("src/retrieval","src/evaluation","src/normalization"):
    sys.path.insert(0,str(ROOT/folder))
from claim_verification import filter_claims, REFUSAL
from hybrid_retrieval import _expand_anchors, rerank_candidates
from normalize_entities import normalize_surface, extraction_payload
from revision_statistics import paired_inference, summarize
from annotation_agreement import cohens_kappa
from snapshot_benchmark import SnapshotGraph, BM25Index, generation_prompt, load_chunks, GeminiREST


class RevisionTests(unittest.TestCase):
    def test_verifier_rejects_fabricated_quote(self):
        answer="Accuracy is 99%."
        result,audit=filter_claims(answer,[{"text":"Accuracy is 70%."}],{"claims":[{
            "text":answer,"supported":True,"context_index":0,"quote":"Accuracy is 99%."}]})
        self.assertEqual(result,REFUSAL)
        self.assertFalse(audit[0]["accepted"])

    def test_verifier_rejects_new_claim_and_accepts_exact_grounding(self):
        contexts=[{"text":"Reported accuracy is 70 percent."}]
        claim={"text":"Reported accuracy is 70 percent.","supported":True,
               "context_index":0,"quote":"Reported accuracy is 70 percent."}
        self.assertNotEqual(filter_claims(claim["text"],contexts,{"claims":[claim]})[0],REFUSAL)
        self.assertEqual(filter_claims("Something else",contexts,{"claims":[claim]})[0],REFUSAL)

    def test_exact_normalization_does_not_merge_semantic_aliases(self):
        self.assertEqual(normalize_surface(" BERT-model "),normalize_surface("bert model"))
        self.assertNotEqual(normalize_surface("BERT"),normalize_surface("Bidirectional Encoder Representations from Transformers"))

    def test_list_payload_is_recovered(self):
        result=extraction_payload({"extraction_result":[{"entities":[{"id":"x"}],"relations":[]}]})
        self.assertEqual(result["entities"],[{"id":"x"}])

    def test_perfect_and_undefined_kappa(self):
        self.assertEqual(cohens_kappa(["a","b"],["a","b"])["cohens_kappa"],1)
        self.assertIsNone(cohens_kappa(["a"],["a"])["cohens_kappa"])
        with self.assertRaises(ValueError): cohens_kappa([""],["a"])

    def test_repeats_are_not_independent_sample_units(self):
        rows=[dict(method=m,question_id=q,repeat=r,total_time=v,error=None)
              for q in range(3) for r in range(5) for m,v in [("kg",1),("bm25",2)]]
        result=summarize(rows,draws=100)
        with_failure=summarize(rows+[dict(method="kg",question_id=99,repeat=1,error="quota",total_time=0)],draws=100)
        self.assertEqual(next(x for x in with_failure["execution_counts"] if x["method"]=="kg")["n_failed"],1)
        test=result["paired_tests"][0]
        self.assertEqual(test["n_questions"],3)
        self.assertEqual(test["mean_difference"],-1)
        with self.assertRaises(ValueError): summarize(rows+[rows[0]],draws=10)

    def test_no_graph_expansion_leaks_neighbors(self):
        class Result:
            def data(self): return [{"connections":[{"related_name":"secret"}],"degree":3}]
        class Session:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def run(self,query,**kwargs):
                self.query=query
                assert "[*0..0]" in query
                return Result()
        class Driver:
            def session(self): return Session()
        rows=_expand_anchors(Driver(),[{"id":"x"}],"all",max_hops=0)
        self.assertEqual(rows[0]["connections"],[])
        self.assertEqual(rows[0]["degree"],0)

    def test_ranking_signal_removal_changes_scores(self):
        candidates=[dict(entity_name="BERT",entity_type="Concept",entity_desc="BERT model",
                         retrieval_score=1,connections=[],source_papers=[]),
                    dict(entity_name="Unrelated",entity_type="Concept",entity_desc="",
                         retrieval_score=20,connections=[],source_papers=[])]
        plan={"search_terms":["BERT"],"entities":[],"expected_labels":[]}
        ranked=rerank_candidates("BERT",plan,copy.deepcopy(candidates))
        removed=rerank_candidates("BERT",plan,copy.deepcopy(candidates),signal_multipliers={"semantic":0})
        self.assertGreater(ranked[0]["ranking"]["score"],0)
        original={x["entity_name"]:x["ranking"]["score"] for x in ranked}
        ablated={x["entity_name"]:x["ranking"]["score"] for x in removed}
        self.assertLess(ablated["BERT"],original["BERT"])

    def test_negative_weight_fails(self):
        with self.assertRaises(ValueError):
            rerank_candidates("x",{},[{"entity_name":"x"}],signal_multipliers={"semantic":-1})

    def test_text_baselines_keep_header_author_evidence(self):
        scratch=(ROOT/"work/test-temp").resolve()
        scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            assert Path(folder).resolve().is_relative_to(scratch)
            p=Path(folder)/"paper.json"
            p.write_text(json.dumps({"filename":"paper.pdf","title":"Example","raw_header":"Alice Researcher and Bob Scientist", "sections":[]}),encoding="utf-8")
            chunks=load_chunks(Path(folder))
            self.assertIn("Alice Researcher",chunks[0]["text"])

    def test_daily_quota_is_not_retried(self):
        error=urllib.error.HTTPError("https://example.invalid",429,"quota",{},
            io.BytesIO(b'{"error":{"message":"per day limit exceeded"}}'))
        with patch("urllib.request.urlopen",side_effect=error) as call, patch("time.sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError,"daily quota"):
                GeminiREST("secret","model").generate("x")
            self.assertEqual(call.call_count,1)
            sleep.assert_not_called()

    def test_generation_prompt_has_no_reference(self):
        prompt=generation_prompt("question",[{"text":"evidence"}])
        self.assertNotIn("ground_truth",prompt)
        self.assertNotIn("reference_answer",prompt)


if __name__=="__main__": unittest.main()
