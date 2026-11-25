import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/extraction'))
from table_evidence import assign_words,valid_box


class TableEvidenceTests(unittest.TestCase):
    def word(self,text,x0,x1):return {'text':text,'x0':x0,'x1':x1,'top':2,'bottom':8}
    def test_column_values_cannot_leak_to_adjacent_column(self):
        cells=[{'id':'a','role':'value','bbox':[0,0,10,10]},{'id':'b','role':'value','bbox':[10,0,20,10]}]
        result=assign_words([self.word('91.2',1,8),self.word('15.8',11,18)],cells,20,10)
        self.assertEqual(result['a']['derived_text'],'91.2');self.assertEqual(result['b']['derived_text'],'15.8')
    def test_number_crossing_boundary_is_blocked_not_truncated(self):
        cells=[{'id':'a','role':'value','bbox':[0,0,10,10]},{'id':'b','role':'value','bbox':[10,0,20,10]}]
        result=assign_words([self.word('734.60',8,14)],cells,20,10)
        for cell in result.values():
            self.assertIn('word_crosses_cell_boundary',cell['issues']);self.assertEqual(cell['derived_text'],'')
    def test_corrupt_character_is_preserved_and_flagged(self):
        result=assign_words([self.word('3.21\ufffd0.01',1,9)],[{'id':'a','role':'value','bbox':[0,0,10,10]}],10,10)['a']
        self.assertEqual(result['derived_text'],'3.21\ufffd0.01')
        self.assertIn('corrupt_pdf_text_requires_ocr_or_transcription',result['issues'])
    def test_bad_coordinates_and_duplicate_or_overlapping_cells_rejected(self):
        for box in ([0,0,float('nan'),2],[0,0,11,2],[3,0,1,2],[True,0,2,2]):
            with self.assertRaises(ValueError):valid_box(box,10,10)
        for second in ({'id':'a','role':'value','bbox':[5,0,9,10]}, {'id':'b','role':'value','bbox':[5,0,9,10]}):
            with self.assertRaises(ValueError):assign_words([], [{'id':'a','role':'value','bbox':[0,0,8,10]},second],10,10)
