import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/extraction'))
from ontology_profiles import signatures,LEGACY,COMPOSITION
from chunk_runner import contract,prompt_for
from reextract_review import validate_extraction
from strict_validation import validate_graph_records
from chunk_merge import merge_tasks


class OntologyProfileTests(unittest.TestCase):
    def setUp(self):
        text='Method A incorporates Method B as an operational component.'
        self.sections=[{'section_id':'s1','text':text}]
        self.payload={'entities':[{'id':name,'name':name,'type':'Method','description':'A method',
            'evidence':[{'section_id':'s1','text':text}]} for name in ['A','B']],
            'relations':[{'source':'A','target':'B','type':'HAS_COMPONENT','evidence':[{'section_id':'s1','text':text}]}]}

    def test_legacy_rejects_extension(self):
        cleaned,issues=validate_extraction(self.payload,self.sections)
        self.assertEqual(cleaned['relations'],[])
        self.assertEqual(issues[0]['reason'],'invalid_relation_type')

    def test_extension_preserves_direction_without_retyping(self):
        before=copy.deepcopy(self.payload)
        cleaned,issues=validate_extraction(self.payload,self.sections,ontology_profile=COMPOSITION)
        self.assertEqual(len(cleaned['relations']),1)
        self.assertEqual(issues,[])
        self.assertEqual(before,self.payload)

    def test_extension_does_not_reinterpret_used_for(self):
        self.payload['relations'][0]['type']='USED_FOR'
        cleaned,issues=validate_extraction(self.payload,self.sections,ontology_profile=COMPOSITION)
        self.assertEqual(cleaned['relations'],[])
        self.assertEqual(issues[0]['reason'],'invalid_type_signature')

    def test_self_component_rejected(self):
        self.payload['relations'][0]['target']='A'
        _,issues=validate_extraction(self.payload,self.sections,ontology_profile=COMPOSITION)
        self.assertEqual(issues[0]['reason'],'self_component_relation')

    def test_schema_prompt_and_registry_agree(self):
        task={'task_id':'t','scope_ids':['e'],'context_ids':[]}
        catalog={'sections_sha256':'hash','items':[{'id':'e','section_id':'s1','kind':'body','text':'Source'}]}
        for profile in (LEGACY,COMPOSITION):
            policy,_=contract(ontology_profile=profile)
            self.assertEqual(set(policy['schema']['properties']['relations']['items']['properties']['type']['enum']),set(signatures(profile)))
            prompt=prompt_for(task,catalog,self.sections,12,profile)
            self.assertNotIn('{{RELATION_CONTRACT}}',prompt)
            self.assertEqual('HAS_COMPONENT' in prompt,profile==COMPOSITION)

    def test_unknown_profile_rejected(self):
        with self.assertRaises(ValueError):signatures('unversioned')

    def test_production_import_rejects_experimental_profile(self):
        with self.assertRaisesRegex(ValueError,'Experimental ontology'):
            validate_graph_records({'filename':'a.json','ontology_profile':COMPOSITION,
                                    'extraction_result':{'entities':[],'relations':[]}})

    def test_merge_respects_same_profile_as_task_validation(self):
        merged,issues,_,_=merge_tasks({'t1':self.payload},self.sections,'a'*64,ontology_profile=COMPOSITION)
        self.assertEqual(len(merged['relations']),1)
        self.assertEqual(issues,[])
        legacy,issues,_,_=merge_tasks({'t1':self.payload},self.sections,'a'*64)
        self.assertEqual(legacy['relations'],[])
