import json
import sys
import unittest
from unittest.mock import Mock
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from reextract_review import ENTITY_TYPES,SIGNATURES
from prompt_library import PROMPT_VERSION


class ProtocolAlignmentTests(unittest.TestCase):
    def test_strict_metric_contract_matches_protocol_and_published_schema(self):
        from strict_validation import FIELDS
        from strict_runner import VERSION
        protocol=json.loads((ROOT/'configs/strict_protocol_v3_1.json').read_text(encoding='utf-8'))
        published=json.loads((ROOT/'schemas/extracted_kg_strict_v3.schema.json').read_text(encoding='utf-8'))
        self.assertEqual(protocol['protocol_id'],VERSION)
        self.assertEqual(protocol['metric_identity_fields'],list(FIELDS))
        self.assertEqual(published['properties']['entities']['items']['properties']['measurement']['required'],list(FIELDS))

    def test_jsonl_preserves_unicode_line_separators_inside_evidence(self):
        sys.path.insert(0,str(ROOT/'src/evaluation'))
        from revision_statistics import load_jsonl
        records=[{'quote':'PDF text\u2028with separator\u2029preserved'}, {'quote':'second record'}]
        path=Mock()
        path.read_text.return_value=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records)
        self.assertEqual(load_jsonl(path),records)

    def test_active_schema_protocol_and_runtime_agree(self):
        protocol=json.loads((ROOT/'configs/review_protocol_v1_1.json').read_text(encoding='utf-8'))
        schema=json.loads((ROOT/'schemas/extracted_kg_review_v2_2.schema.json').read_text(encoding='utf-8'))
        payload=schema['properties']['extraction_result']['properties']
        self.assertEqual(protocol['entity_types'],ENTITY_TYPES)
        self.assertEqual(protocol['extraction_prompt_version'],PROMPT_VERSION)
        self.assertEqual(protocol['relation_signatures'],{k:list(v) for k,v in SIGNATURES.items()})
        self.assertEqual(payload['entities']['items']['properties']['type']['enum'],ENTITY_TYPES)
        self.assertEqual(set(payload['relations']['items']['properties']['type']['enum']),set(SIGNATURES))
