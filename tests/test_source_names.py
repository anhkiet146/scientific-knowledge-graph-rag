import copy
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from evidence_catalog import build_catalog
from strict_runner import evaluate
from reextract_review import validate_extraction


class SourceNameTests(unittest.TestCase):
    def test_opaque_author_id_does_not_need_to_appear_in_header(self):
        sections=[{'section_id':'s001','kind':'header','text':'Alice Doe, Example University.'}]
        catalog=build_catalog(sections);eid=catalog['items'][0]['id']
        payload={'entities':[{'id':'e1','name':'Alice Doe','type':'Author','description':'author','evidence_ids':[eid]}],'relations':[]}
        accepted,issues,blockers=evaluate(payload,catalog,sections)
        self.assertFalse(issues)
        self.assertEqual(accepted['entities'][0]['id'],'e1')
        self.assertEqual(accepted['entities'][0]['name'],'Alice Doe')

    def test_correct_id_or_description_cannot_rescue_invented_source_name(self):
        sections=[{'section_id':'s001','kind':'header','text':'Author Alice Doe, Example University.'}]
        payload={'entities':[{'id':'Alice Doe','name':'Alice Smith','type':'Author','description':'Alice Doe',
                  'evidence':[{'section_id':'s001','text':sections[0]['text']}]}],'relations':[]}
        accepted,issues=validate_extraction(payload,sections,require_names=True)
        self.assertEqual(accepted['entities'],[])
        self.assertEqual(issues[0]['reason'],'name_not_grounded_in_header')

    def test_named_entity_relations_still_use_ids(self):
        sections=[{'section_id':'s001','kind':'header','text':'Alice Doe is affiliated with Example University.'}]
        catalog=build_catalog(sections);eid=catalog['items'][0]['id']
        entities=[{'id':i,'name':n,'type':t,'description':'source role','evidence_ids':[eid]}
                  for i,n,t in [('a1','Alice Doe','Author'),('i1','Example University','Institution')]]
        payload={'entities':entities,'relations':[{'source':'a1','target':'i1','type':'AFFILIATED_WITH','evidence_ids':[eid]}]}
        accepted,issues,_=evaluate(payload,catalog,sections)
        self.assertFalse(issues)
        self.assertEqual(accepted['relations'][0]['source'],'a1')
        bad=copy.deepcopy(payload);bad['relations'][0]['source']='Alice Doe'
        _,issues,_=evaluate(bad,catalog,sections)
        self.assertTrue(issues)

    def test_names_are_required_in_new_transport(self):
        sections=[{'section_id':'s001','text':'Method A was applied.'}]
        catalog=build_catalog(sections)
        with self.assertRaises(ValueError):evaluate({'entities':[{'id':'a','type':'Method','description':'applied','evidence_ids':[catalog['items'][0]['id']]}],'relations':[]},catalog,sections)
