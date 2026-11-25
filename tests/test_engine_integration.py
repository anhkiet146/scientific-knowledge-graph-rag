"""SDK-backed imports with fake services; no paid calls and no database writes."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
for folder in (ROOT, ROOT/"src/retrieval",ROOT/"src/graph_construction"):
    sys.path.insert(0,str(folder))
try:
    import graphrag_engine as engine
    from build_graph import KnowledgeGraphBuilder
    READY=True
except ImportError:
    READY=False


@unittest.skipUnless(READY,"Install google-genai, neo4j and python-dotenv")
class EngineIntegrationTests(unittest.TestCase):
    def test_actual_context_is_returned_and_options_forwarded(self):
        context=[{"entity_name":"Example","entity_type":"Concept","entity_desc":"source evidence"}]
        responses=[json.dumps({"keywords":["Example"],"answer_type":"entity"}),"Supported answer"]
        with patch.object(engine,"_call_gemini",side_effect=responses), \
             patch.object(engine,"_get_driver",return_value=object()), \
             patch.object(engine,"retrieve_candidates",return_value=(context,{})) as retrieve, \
             patch.object(engine,"rerank_candidates",return_value=context) as rerank, \
             patch.object(engine,"select_highlight_nodes",return_value=["highlight only"]):
            answer,nodes,timings=engine.ask_graphrag("Example?",evaluation_mode=True,max_hops=0,signal_multipliers={"semantic":0})
        self.assertEqual(timings["retrieved_context"],context)
        self.assertNotEqual(timings["retrieved_context"],nodes)
        self.assertEqual(retrieve.call_args.kwargs["max_hops"],0)
        self.assertEqual(rerank.call_args.kwargs["signal_multipliers"],{"semantic":0})
        self.assertGreaterEqual(timings["total_ms"],timings["retrieval_ms"])

    def test_retrieval_failure_is_machine_readable(self):
        with patch.object(engine,"_call_gemini",return_value='{"keywords":["x"]}'), \
             patch.object(engine,"_get_driver",return_value=object()), \
             patch.object(engine,"retrieve_candidates",side_effect=RuntimeError("unavailable")):
            _,_,timings=engine.ask_graphrag("Example?",evaluation_mode=True)
        self.assertEqual(timings["error"]["stage"],"retrieval")

    def test_graph_relation_is_type_constrained(self):
        from test_strict_workflow import reviewed_graph,FakeDriver
        builder=KnowledgeGraphBuilder.__new__(KnowledgeGraphBuilder);builder.driver=FakeDriver()
        result=builder.load_paper_data(reviewed_graph())
        relation=[q for q,k in builder.driver.committed if "MERGE (a)-" in q][0]
        self.assertIn("MATCH (a:`Method`",relation)
        self.assertIn("MATCH (b:`Concept`",relation)
        self.assertEqual(result["relations_saved"],1)

    def test_graph_uses_mentions_for_provenance_and_retains_evidence(self):
        from test_strict_workflow import reviewed_graph,FakeDriver
        builder=KnowledgeGraphBuilder.__new__(KnowledgeGraphBuilder);builder.driver=FakeDriver()
        data=reviewed_graph();builder.load_paper_data(data)
        provenance=[(q,k) for q,k in builder.driver.committed if "MENTIONS" in q]
        self.assertEqual(len(provenance),2)
        semantic=[(q,k) for q,k in builder.driver.committed if "MERGE (a)-" in q][0]
        self.assertEqual(json.loads(semantic[1]["record"])["evidence"],data["extraction_result"]["relations"][0]["evidence"])
        data["extraction_result"]["relations"][0]["type"]="RELATED_TO"
        with self.assertRaises(ValueError):builder.load_paper_data(data)


if __name__=="__main__": unittest.main()
