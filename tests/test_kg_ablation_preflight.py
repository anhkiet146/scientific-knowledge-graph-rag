import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/evaluation'))
from snapshot_benchmark import SnapshotGraph
from context_budget import pack
from hybrid_retrieval import build_query_plan


class KGAblationPreflightTests(unittest.TestCase):
    def test_explicit_author_identity_overrides_topic_metric_or_relationship(self):
        for question in ('Who are the authors of the study on growth rate?',
            'Các tác giả của nghiên cứu về nồng độ muối là ai?',
            'Who wrote the paper about dataset relationships?'):
            self.assertEqual(build_query_plan(question)['answer_type'],'author')
    def test_author_mention_does_not_override_actual_method_or_value_question(self):
        self.assertEqual(build_query_plan('Which method did the authors use for cell detection?')['answer_type'],'method')
        self.assertEqual(build_query_plan('What percentage did the authors report?')['answer_type'],'metric')
    def test_no_expansion_removes_neighbor_connections_and_degree(self):
        with tempfile.TemporaryDirectory() as tmp:
            source={'filename':'paper','paper_title':'Experiment','extraction_result':{
                'entities':[{'id':'Model X','type':'Method','description':'A model'},
                    {'id':'Target task','type':'Concept','description':'Detection'}],
                'relations':[{'source':'Model X','target':'Target task','type':'USED_FOR'}]}}
            (Path(tmp)/'paper.json').write_text(json.dumps(source),encoding='utf-8')
            graph=SnapshotGraph(Path(tmp))
            plain=graph.retrieve('Model X',hops=0,anchor_limit=1)
            expanded=graph.retrieve('Model X',hops=2,anchor_limit=1)
            self.assertEqual(len(plain),1)
            self.assertTrue(all(not c['connections'] and c['degree']==0 and c['hop_distance']==0 for c in plain))
            self.assertGreater(len(expanded),len(plain));self.assertTrue(any(c['degree']>0 for c in expanded))
    def test_generic_graph_packing_does_not_fabricate_chunk_id(self):
        row={'entity_name':'Model X','entity_type':'Method','connections':[]}
        result,text,count=pack([row],list,1000)
        self.assertEqual(result,[row]);self.assertNotIn('chunk_id',result[0]);self.assertEqual(count,len(text))
    def test_oversized_first_graph_record_is_reportable_empty_not_silently_skipped(self):
        first={'entity_desc':'x'*100};second={'entity_desc':'y'}
        result,text,_=pack([first,second],list,30)
        self.assertEqual(result,[]);self.assertEqual(text,'[]')
