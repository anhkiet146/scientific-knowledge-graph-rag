import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/extraction'))
from table_measurements import parse_numeric,superscript_markers,build_candidates


class TableMeasurementTests(unittest.TestCase):
    def test_inline_time_and_unitless_fraction(self):
        value=parse_numeric('14.5 sec');self.assertEqual(value['value'],'14.5');self.assertEqual(value['unit'],'sec')
        self.assertEqual(parse_numeric('1.00000')['unit'],'')
        self.assertEqual(parse_numeric('14.5 s',footnotes={'s'})['unit'],'s')
    def test_header_unit_uncertainty_and_verified_footnote(self):
        value=parse_numeric('734.60±20.80d',header='IC50 (µg/mL)',footnotes={'d'})
        self.assertEqual((value['value'],value['unit'],value['uncertainty'],value['footnote_marker']),('734.60','µg/mL','20.80','d'))
        with self.assertRaises(ValueError):parse_numeric('734.60±20.80d',header='IC50 (µg/mL)')
    def test_scientific_notation_is_preserved_without_conversion(self):
        self.assertEqual(parse_numeric('3.2838e – 04')['value'],'3.2838e – 04')
    def test_ambiguous_units_annotations_and_corruption_are_rejected(self):
        for text in ('high','3.21\ufffd0.01','3.21 mg/mL garbage','1-2','3.21d'):
            with self.assertRaises(ValueError):parse_numeric(text)
        with self.assertRaises(ValueError):parse_numeric('3.21 mg/mL',header='IC50 (µg/mL)')
        with self.assertRaises(ValueError):parse_numeric('3.21±-0.01')
    def test_superscript_requires_geometric_support(self):
        cell={'glyphs':[{'text':'1','size':10,'bbox':[0,3,4,13]}, {'text':'d','size':6,'bbox':[4,2,6,8]},
            {'text':'s','size':10,'bbox':[6,3,10,13]}]}
        self.assertEqual(superscript_markers(cell),{'d'})
    def fixture(self):
        fields={'caption':'Table 2','endpoint':'Training time','object':'Model A','value':'14.5 sec',
            'condition':'20','condition_label':'Epochs'}
        return {'source_sha256':'a'*64,'table_id':'t2','page':5,
            'cells':[{'id':k,'role':k,'derived_text':v,'issues':[],'glyphs':[]} for k,v in fields.items()],
            'observations':[{'id':'o1','cell_refs':{k:k for k in fields},'derived_fields':fields}]}
    def test_candidate_preserves_condition_header_and_has_no_approval(self):
        result=build_candidates(self.fixture());candidate=result['candidates'][0]
        self.assertEqual(candidate['measurement']['condition'],'Epochs 20')
        self.assertEqual(candidate['measurement']['object'],'Model A')
        self.assertFalse(result['approved_for_graph'])
        self.assertEqual(candidate['status'],'pending_layout_and_semantic_review')
    def test_tampered_mapping_or_missing_condition_label_rejected(self):
        table=self.fixture();table['observations'][0]['derived_fields']['value']='99.9 sec'
        with self.assertRaises(ValueError):build_candidates(table)
        table=self.fixture();del table['observations'][0]['cell_refs']['condition_label'];del table['observations'][0]['derived_fields']['condition_label']
        result=build_candidates(table)
        self.assertEqual(result['candidates'][0]['status'],'blocked')
    def test_source_issues_block_measurement_creation(self):
        table=self.fixture();table['cells'][0]['issues']=['word_crosses_cell_boundary']
        record=build_candidates(table)['candidates'][0]
        self.assertEqual(record['status'],'blocked');self.assertIsNone(record['measurement'])
