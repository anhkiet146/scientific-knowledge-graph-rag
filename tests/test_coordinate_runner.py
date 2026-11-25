import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/extraction'))
from coordinate_runner import field_provenance,run
from graph_policy import require_graph_review
from workflow_io import atomic_json,read_json


class CoordinateRunnerTests(unittest.TestCase):
    def bundle(self):
        return {'protocol_id':'coordinate-table-bundle-v1','table_evidence':{'source_sha256':'a'*64},
            'measurements':{'candidates':[{'review_id':'r1','observation_id':'o1','status':'pending_layout_and_semantic_review'}]}}
    def inputs(self,base):
        for name in ('source.pdf','spec.json','evidence.json'):(base/name).write_text('{}',encoding='utf-8')
        jobs=base/'jobs.json'
        atomic_json(jobs,[{'id':'table1','pdf':'source.pdf','spec':'spec.json','evidence':'evidence.json'}])
        return jobs,base/'run'
    def test_no_approval_and_stable_resume_preserves_template(self):
        with tempfile.TemporaryDirectory() as tmp,patch('coordinate_runner.verified_bundle',side_effect=lambda **_:self.bundle()):
            jobs,output=self.inputs(Path(tmp));first=run(jobs,output)
            template=(output/'review_template.json').read_bytes();second=run(jobs,output)
            self.assertEqual(first,second);self.assertEqual(template,(output/'review_template.json').read_bytes())
            self.assertEqual(first['actual_api_calls'],0);self.assertEqual(first['approved_for_graph'],0)
            self.assertEqual(first['status'],'pending_human_review')
    def test_tampered_snapshot_or_bundle_blocks_resume(self):
        for name in ('sources/table1/pdf.pdf','tables/table1.json','policy_snapshot/coordinate_runner.py'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp,patch('coordinate_runner.verified_bundle',side_effect=lambda **_:self.bundle()):
                jobs,output=self.inputs(Path(tmp));run(jobs,output);(output/name).write_text('{}',encoding='utf-8')
                # source.pdf fixture starts as {}, so give it a distinct mutation.
                if name.endswith('.pdf'):(output/name).write_text('changed',encoding='utf-8')
                with self.assertRaises(ValueError):run(jobs,output)
    def test_failing_source_replay_emits_no_candidate_directory(self):
        with tempfile.TemporaryDirectory() as tmp,patch('coordinate_runner.verified_bundle',side_effect=ValueError('Invalid PDF source')):
            jobs,output=self.inputs(Path(tmp))
            with self.assertRaises(ValueError):run(jobs,output)
            self.assertFalse(output.exists())
    def test_job_id_cannot_escape_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs,output=self.inputs(Path(tmp));data=read_json(jobs);data[0]['id']='../escape';atomic_json(jobs,data)
            with self.assertRaises(ValueError):run(jobs,output)
            self.assertFalse(output.exists())
    def test_direct_graph_import_cannot_be_enabled_by_adding_review(self):
        for protocol in ('coordinate-table-bundle-v1','coordinate-measurement-candidates-v1','coordinate-table-pilot-v1'):
            with self.assertRaisesRegex(ValueError,'direct import is disabled'):
                require_graph_review({'protocol_id':protocol,'review':{'decision':'approved'}})
    def test_field_provenance_keeps_header_and_row_condition_together(self):
        refs={k:k for k in ('value','unit','endpoint','object','condition','condition_label','caption')}
        table={'cells':[{'id':k,'evidence_id':'ev_'+k} for k in refs]}
        row={'source_cell_refs':refs,'measurement':{k:'test' for k in ('value','unit','endpoint','object','condition','source_report','uncertainty')}}
        provenance=field_provenance(row,table)
        self.assertEqual(provenance['condition']['cell_ids'],['condition_label','condition'])
        self.assertEqual(provenance['endpoint']['cell_ids'],['unit','endpoint'])
        self.assertEqual(provenance['uncertainty']['cell_ids'],['value'])
