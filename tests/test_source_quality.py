import copy
import contextlib
import io
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/extraction'))
from source_quality import split_page, quality_report
from reextract_review import sections_from_document, validate_extraction
import reextract_review


class SourceQualityTests(unittest.TestCase):
    def test_preflight_can_resume_with_equivalent_integer_float_rate(self):
        root=Path(__file__).resolve().parents[1]
        parent=(root/'work').resolve()
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            workspace=Path(folder).resolve()
            self.assertTrue(workspace.is_relative_to(parent))
            source=workspace/'input';source.mkdir()
            (source/'paper.json').write_text(json.dumps({'title':'Pilot source'}),encoding='utf-8')
            args=['runner','--input',str(source),'--output',str(workspace/'output'),'--preflight']
            with patch.object(sys,'argv',args),contextlib.redirect_stdout(io.StringIO()):
                reextract_review.main()
            with patch.object(sys,'argv',args+['--requests-per-minute','4']),contextlib.redirect_stdout(io.StringIO()):
                reextract_review.main()

    def test_undamaged_layout_is_preserved_exactly(self):
        text='Model    Accuracy\nA        0.91\n\nB        0.87'
        fragments,rejected=split_page(text)
        self.assertEqual(rejected,[])
        self.assertEqual(fragments[0]['text'],text)

    def test_damaged_lines_are_excluded_without_joining_fragments(self):
        text='Learner A is applied.\nEquation = \ufffd beta\nAccuracy was 0.91.'
        source={'sections':[{'category':'pdf_page','page':4,'section_title':'PDF page 4','content':text}]}
        original=copy.deepcopy(source)
        sections=sections_from_document(source)
        self.assertEqual(len(sections),2)
        self.assertEqual(sections[0]['last_line'],1)
        self.assertEqual(sections[1]['first_line'],3)
        self.assertEqual(sections[1]['page'],4)
        self.assertNotIn('\ufffd',''.join(s['text'] for s in sections))
        self.assertEqual(source,original)
        quality=quality_report(source)
        self.assertEqual(quality['excluded_lines'],1)
        self.assertFalse(quality['original_source_changed'])
        payload={'entities':[{'id':'Learner A','type':'Method','description':'applied',
                             'evidence':[{'section_id':sections[0]['section_id'],
                                          'text':'Learner A is applied. Accuracy was 0.91.'}]}], 'relations':[]}
        accepted,issues=validate_extraction(payload,sections)
        self.assertEqual(accepted['entities'],[])
        self.assertEqual(issues[0]['reason'],'no_grounded_source_quote')

    def test_fully_damaged_page_provides_no_quoteable_placeholder(self):
        fragments,rejected=split_page('bad \ufffd\nother \ufffd')
        self.assertEqual(fragments,[])
        self.assertEqual(len(rejected),2)

    def test_corrupt_quote_is_rejected_even_in_metadata(self):
        sections=[{'section_id':'s000','kind':'abstract','text':'Reported accuracy was \ufffd 0.91.'}]
        payload={'entities':[{'id':'accuracy 0.91','type':'Metric','description':'reported',
                             'evidence':[{'section_id':'s000','text':sections[0]['text']}]}],'relations':[]}
        accepted,issues=validate_extraction(payload,sections)
        self.assertEqual(accepted['entities'],[])
