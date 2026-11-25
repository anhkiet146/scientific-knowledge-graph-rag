from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/extraction'))
from evidence_catalog import build_catalog
from chunk_contract import evaluate_task


class ScopeOutputTests(unittest.TestCase):
    def test_context_only_relation_is_removed_from_cleaned_output(self):
        sections=[{'section_id':'s1','kind':'body','text':'Method A incorporates Method B as a component.'},
                  {'section_id':'s2','kind':'body','text':'A different finding is in the current task.'}]
        catalog=build_catalog(sections);ctx,scope=[i['id'] for i in catalog['items']]
        payload={'entities':[{'id':key,'name':'Method '+key,'type':'Method','description':'Method',
                            'evidence_ids':[ctx]} for key in ('A','B')],
                 'relations':[{'source':'A','target':'B','type':'HAS_COMPONENT','evidence_ids':[ctx]}],
                 'completion':{'status':'complete','remaining_scope_ids':[]}}
        cleaned,issues,_,_=evaluate_task(payload,{'task_id':'t','scope_ids':[scope],'context_ids':[ctx]},catalog,sections,
                                        ontology_profile='composition-experimental-v1')
        self.assertEqual(len(cleaned['entities']),2)
        self.assertEqual(cleaned['relations'],[])
        self.assertIn('relation_outside_task_scope',[i['reason'] for i in issues])

    def test_context_only_measurement_and_dependent_edge_are_removed(self):
        sections=[{'section_id':'s1','kind':'body','text':'Model A achieved accuracy of 92.1%.'},
                  {'section_id':'s2','kind':'body','text':'The current task reports another finding.'}]
        catalog=build_catalog(sections);ctx,scope=[i['id'] for i in catalog['items']]
        payload={'entities':[{'id':'A','name':'Model A','type':'Method','description':'Method','evidence_ids':[ctx]},
            {'id':'M','name':'accuracy','type':'Metric','description':'Measured accuracy','evidence_ids':[ctx],
             'measurement':{'endpoint':'accuracy','value':'92.1','unit':'%','object':'Model A','condition':'',
                            'uncertainty':'','source_report':'prose'}}],
            'relations':[{'source':'A','target':'M','type':'ACHIEVED','evidence_ids':[ctx]}],
            'completion':{'status':'complete','remaining_scope_ids':[]}}
        cleaned,issues,_,_=evaluate_task(payload,{'task_id':'t','scope_ids':[scope],'context_ids':[ctx]},catalog,sections)
        self.assertEqual([e['id'] for e in cleaned['entities']],['A'])
        self.assertEqual(cleaned['relations'],[])
        self.assertIn('measurement_outside_task_scope',[i['reason'] for i in issues])
