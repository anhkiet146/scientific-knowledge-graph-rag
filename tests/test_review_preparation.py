import copy
import csv
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src/extraction')]
from prepare_annotation_v3_1 import prepare
from prepare_review_execution_plan import budget
from workflow_io import atomic_json,read_json,file_hash


class ReviewPreparationTests(unittest.TestCase):
    def inputs(self,root):
        for name in ('corpus','pdfs','development'):(root/name).mkdir()
        atomic_json(root/'corpus/paper.json',{'title':'Source paper','abstract':'Source abstract.',
            'sections':[{'title':'Body','content':'A complete original source paragraph.'}]})
        (root/'pdfs/paper.pdf').write_bytes(b'synthetic fixture, not a real article')
        sample=root/'sample.csv'
        with sample.open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=['paper_id','filename','source_sha256']);writer.writeheader()
            writer.writerow({'paper_id':'p1','filename':'paper.pdf','source_sha256':'historical-different-parser'})
        questions=root/'questions.py';questions.write_text("data=[{'question':'What was measured?','ground_truth':'SECRET OLD ANSWER','chatbot_answer':'SECRET MODEL OUTPUT'}]",encoding='utf-8')
        return dict(sample=sample,corpus=root/'corpus',pdfs=root/'pdfs',development=root/'development',questions=questions,
            output=root/'bundle',expected_papers=1,expected_questions=1)
    def test_blank_bundle_uses_current_protocol_separate_hashes_and_no_answer_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=self.inputs(Path(tmp));manifest=prepare(**args)
            task=read_json(args['output']/'annotator_A_qa.json')['tasks'][0]
            self.assertIsNone(task['reference_answer']);self.assertEqual(task['annotation_status'],'pending')
            for p in args['output'].glob('annotator*'):
                text=p.read_text(encoding='utf-8');self.assertNotIn('SECRET',text)
            row=__import__('json').loads((args['output']/'annotator_A_extraction.jsonl').read_text(encoding='utf-8'))
            self.assertEqual(row['protocol_id'],'strict-extraction-v3.1')
            self.assertEqual(row['source_sha256'],file_hash(args['corpus']/'paper.json'))
            self.assertEqual(row['source_pdf_sha256'],file_hash(args['pdfs']/'paper.pdf'))
            self.assertFalse(manifest['independent_gold_ready'])
    def test_development_overlap_or_existing_output_cannot_silently_reselect(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=self.inputs(Path(tmp));atomic_json(args['development']/'paper.json',{})
            with self.assertRaises(ValueError):prepare(**args)
            self.assertFalse(args['output'].exists())
        with tempfile.TemporaryDirectory() as tmp:
            args=self.inputs(Path(tmp));prepare(**args)
            with self.assertRaises(ValueError):prepare(**args)
    def test_budget_has_unknown_total_and_includes_all_declared_online_stages(self):
        result=budget(45,5,8)
        self.assertEqual(result['online_scenario_calls'],2700)
        self.assertEqual(result['components']['controlled_answer_calls'],1800)
        self.assertIsNone(result['full_total_calls']);self.assertIsNone(result['cost_money'])
        self.assertIsNone(result['released_indexing_calls'])
    def test_boolean_or_zero_design_counts_rejected(self):
        for values in ((True,5,8),(45,0,8),(45,5,0)):
            with self.assertRaises(ValueError):budget(*values)
