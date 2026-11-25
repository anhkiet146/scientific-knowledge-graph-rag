import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/extraction'))
from evidence_catalog import build_catalog, materialize, transport_schema
from reextract_review import validate_extraction, schema


class EvidenceCatalogTests(unittest.TestCase):
    def test_transport_schema_removes_quote_copy_without_mutating_active_schema(self):
        active=schema();transport=transport_schema(active)
        self.assertIn('evidence',active['properties']['entities']['items']['properties'])
        self.assertNotIn('evidence',transport['properties']['entities']['items']['properties'])
        self.assertIn('evidence_ids',transport['properties']['relations']['items']['required'])

    def test_ids_resolve_to_exact_source_without_model_quote_copy(self):
        sections=[{'section_id':'s001','kind':'body','text':'Learner A was used to solve Task X.'}]
        catalog=build_catalog(sections)
        payload={'entities':[{'id':'Learner A','type':'Method','description':'applied',
                              'evidence_ids':[catalog['items'][0]['id']]}],'relations':[]}
        resolved,issues=materialize(payload,catalog,sections)
        self.assertFalse(issues)
        accepted,rejected=validate_extraction(resolved,sections)
        self.assertFalse(rejected)
        self.assertEqual(accepted['entities'][0]['evidence'][0]['text'],sections[0]['text'])

    def test_unknown_ids_and_reconstructed_quotes_are_not_accepted(self):
        sections=[{'section_id':'s001','text':'Actual source text.'}]
        payload={'relations':[],'entities':[{'id':'guess','type':'Concept','evidence_ids':['q99999'],
                              'evidence':[{'section_id':'s001','text':'invented quote'}]}]}
        resolved,issues=materialize(payload,build_catalog(sections),sections)
        self.assertEqual(resolved['entities'],[])
        self.assertEqual(issues[0]['reason'],'missing_or_unknown_evidence_id')

    def test_cross_article_catalog_or_edited_text_cannot_be_used(self):
        sections=[{'section_id':'s001','text':'First article source.'}]
        catalog=build_catalog(sections)
        with self.assertRaises(ValueError):materialize({"entities":[],"relations":[]},catalog,[{'section_id':'s001','text':'Other article source.'}])
        modified=copy.deepcopy(catalog);modified['items'][0]['text']='invented'
        with self.assertRaises(ValueError):materialize({"entities":[],"relations":[]},modified,sections)

    def test_layout_rows_remain_separate_and_offsets_are_exact(self):
        sections=[{'section_id':'s001','text':'Model     Accuracy\nLearner A 0.91\n'+'word '*200}]
        catalog=build_catalog(sections,max_characters=80)
        self.assertEqual(catalog['items'][0]['text'],'Model     Accuracy')
        self.assertEqual(catalog['items'][1]['text'],'Learner A 0.91')
        for item in catalog['items']:
            self.assertEqual(sections[0]['text'][item['start']:item['end']],item['text'])
            self.assertLessEqual(len(item['text']),80)
