import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from normalization_review_study import study,surface

class NormalizationStudyTests(unittest.TestCase):
    def test_scientific_signs_not_erased(self):
        self.assertNotEqual(surface('Dose +1'),surface('Dose -1'))
        self.assertNotEqual(surface('Model-A'),surface('Model A'))

    def test_alias_is_proposal_and_cross_paper_identity_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'input';source.mkdir()
            data={'entities':[{'id':'Gas chromatography (GC)','type':'Method'},{'id':'Task','type':'Concept'}],
                  'relations':[{'source':'GC','target':'Task','type':'USED_FOR'}]}
            original=json.dumps(data)
            for n in ('a','b'):(source/(n+'.json')).write_text(original,encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):study(source,root/'output')
            summary=json.loads((root/'output/summary.json').read_text())
            self.assertEqual(summary['proposed_alias_endpoints'],2)
            self.assertEqual(summary['relation_states']['quarantined'],2)
            self.assertEqual(summary['structural_comparison']['surface']['nodes'],4)
            self.assertEqual((source/'a.json').read_text(),original)

    def test_metric_records_not_merged_and_wrong_direction_quarantined(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'input';source.mkdir()
            data={'entities':[{'id':'Accuracy','type':'Metric'},{'id':'Accuracy','type':'Metric'},
                {'id':'Field','type':'Domain'},{'id':'Task','type':'Concept'}],
                'relations':[{'source':'Field','target':'Task','type':'BELONGS_TO'}]}
            (source/'a.json').write_text(json.dumps(data),encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):study(source,root/'out')
            summary=json.loads((root/'out/summary.json').read_text())
            self.assertEqual(summary['structural_comparison']['surface']['nodes'],4)
            self.assertEqual(summary['relation_states']['quarantined'],1)
