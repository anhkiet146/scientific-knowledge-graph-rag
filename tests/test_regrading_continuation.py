import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from continue_qa_regrading import load_previous
from workflow_io import atomic_json,canonical_hash


class RegradingContinuationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        atomic_json(self.root/'manifest.json',dict(cases=135,model='gemini-2.5-flash',temperature=0,thinking_budget=0,max_output_tokens=2048))
        for i in range(1,136):atomic_json(self.root/'cases'/f'{i:03}.json',dict(case_id=i,prompt='prompt',context='Value 12',method='kg',question_id=i))
        grade=dict(faithfulness=1,relevancy=1,context_precision=1,context_recall=1,unsupported_answer=False,
            controlled_refusal=False,reference_concern=False,rationale='Supported',evidence_quotes=['Value 12'])
        atomic_json(self.root/'grades/001.json',dict(case_id=1,prompt_sha256=canonical_hash('prompt'),method='kg',question_id=1,grade=grade))

    def test_completed_grade_is_reused_without_call(self):
        _,cases,grades=load_previous(self.root)
        self.assertEqual(len(cases),135);self.assertEqual(set(grades),{1})

    def test_changed_prompt_rejected(self):
        p=self.root/'cases/001.json';case=json.loads(p.read_text());case['prompt']='tampered';atomic_json(p,case)
        with self.assertRaises(ValueError):load_previous(self.root)

    def test_changed_judge_contract_rejected(self):
        p=self.root/'manifest.json';m=json.loads(p.read_text());m['model']='different';atomic_json(p,m)
        with self.assertRaises(ValueError):load_previous(self.root)


if __name__=='__main__':unittest.main()
