import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_table_measurements as fixtures
from workflow_io import atomic_json

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prepare_verified_tables',ROOT/'scripts/prepare_table_measurements.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class TableMeasurementVerificationTests(unittest.TestCase):
    def test_adapter_requires_fresh_source_regeneration_before_candidates(self):
        table=fixtures.TableMeasurementTests().fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);layout=root/'spec.json';evidence=root/'evidence.json';pdf=root/'source.pdf'
            atomic_json(layout,{'layout':'source-bound'});atomic_json(evidence,table)
            with patch.object(module,'extract_table',return_value=table) as extract:
                result=module.prepare(pdf,layout,evidence)
            extract.assert_called_once_with(pdf,{'layout':'source-bound'})
            self.assertTrue(result['verified_pdf_and_cell_mapping'])
            self.assertFalse(result['approved_for_graph'])

    def test_even_glyph_only_evidence_tampering_is_rejected(self):
        table=fixtures.TableMeasurementTests().fixture();altered=copy.deepcopy(table)
        altered['cells'][0]['glyphs']=[{'text':'d','size':6,'bbox':[0,0,1,1]}]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);atomic_json(root/'spec.json',{});atomic_json(root/'evidence.json',altered)
            with patch.object(module,'extract_table',return_value=table):
                with self.assertRaisesRegex(ValueError,'Evidence changed'):
                    module.prepare(root/'source.pdf',root/'spec.json',root/'evidence.json')
