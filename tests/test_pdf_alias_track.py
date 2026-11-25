import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from normalization_review_study import study
from verify_normalization_aliases import declaration_pattern,run

class PDFAliasTests(unittest.TestCase):
    def test_literal_declaration_and_word_boundary(self):
        p=declaration_pattern('Gas chromatography','GC-MS')
        self.assertIsNotNone(p.search('Gas\nchromatography (GC -MS)'))
        self.assertIsNone(p.search('Gas chromatography and GC-MS are mentioned separately'))
        self.assertIsNone(p.search('OtherGas chromatography (GC-MS)'))

    def test_literal_policy_preserves_case_in_declaration(self):
        strict=declaration_pattern('Model X','MX',case_sensitive=True)
        self.assertIsNotNone(strict.search('Model X (MX) was evaluated.'))
        self.assertIsNone(strict.search('Model X (mx) was evaluated.'))
        self.assertIsNotNone(declaration_pattern('Model X','MX').search('Model X (mx)'))

    def test_typed_alias_resolves_only_with_literal_pdf_declaration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir();pdfs=root/'pdfs';pdfs.mkdir()
            data={'entities':[{'id':'Gas chromatography (GC)','type':'Method'},{'id':'Task','type':'Concept'}],
                  'relations':[{'source':'GC','target':'Task','type':'USED_FOR'}]}
            (source/'a.json').write_text(json.dumps(data));(pdfs/'a.pdf').write_bytes(b'fixture')
            with contextlib.redirect_stdout(io.StringIO()):study(source,root/'study')
            class Page:
                def extract_text(self):return 'Gas chromatography (GC) was used.'
            class Reader:pages=[Page()]
            with patch('verify_normalization_aliases.PdfReader',return_value=Reader()),contextlib.redirect_stdout(io.StringIO()):run(root/'study',pdfs,root/'result')
            summary=json.loads((root/'result/summary.json').read_text())
            self.assertEqual(summary['rescued_typed_relations'],1)
            self.assertFalse(summary['approved_for_production_graph'])
            self.assertFalse(summary['quality_scores_computed'])
