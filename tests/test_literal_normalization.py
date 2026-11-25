import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from normalization_review_study import literal_surface,study


class LiteralNormalizationTests(unittest.TestCase):
    def test_scientific_variants_remain_distinct(self):
        for left,right in [('pH','PH'),('x²','x2'),('Model-A','Model A'),
                           ('Dose +1','Dose -1'),('Weiß','Weiss'),('α','a')]:
            self.assertNotEqual(literal_surface(left),literal_surface(right))

    def test_canonical_unicode_and_spacing_equivalent(self):
        self.assertEqual(literal_surface(' Cafe\u0301   model '),literal_surface('Café model'))

    def test_invalid_names_and_policy_rejected(self):
        for value in ['',None,42]:
            with self.assertRaises(ValueError):
                literal_surface(value)
        with self.assertRaises(ValueError):
            study(Path('missing'),Path('unused'),'unsafe')

    def test_scope_metrics_and_source_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir()
            entity=lambda name,kind='Method':dict(id=name,type=kind)
            data=dict(entities=[entity('pH'),entity('PH'),entity('x²'),entity('x2'),
                                entity('Accuracy','Metric'),entity('Accuracy','Metric')],relations=[])
            text=json.dumps(data,ensure_ascii=False)
            for name in ['a','b']:
                (source/(name+'.json')).write_text(text,encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                study(source,root/'out','paper_literal_v2')
            report=json.loads((root/'out/summary.json').read_text(encoding='utf-8'))
            self.assertEqual(report['surface_policy'],'paper_literal_v2')
            self.assertEqual(report['structural_comparison']['surface']['nodes'],12)
            self.assertEqual((source/'a.json').read_text(encoding='utf-8'),text)
