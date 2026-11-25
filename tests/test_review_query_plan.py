import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/retrieval'))
from review_query_plan import build_plan

class ReviewPlannerTests(unittest.TestCase):
    def test_gloss_does_not_become_required_identity(self):
        p=build_plan('Which architecture is the backbone (feature extraction network) of ModelX?')
        self.assertNotIn('feature extraction network',p['entities'])
        self.assertIn('feature extraction network',p['soft_parenthetical_terms'])
        self.assertIn('ModelX',p['required_entities'])

    def test_acronym_constraint_preserved(self):
        p=build_plan('Which dataset was evaluated with the system (ABC)?')
        self.assertIn('ABC',p['entities'])

    def test_definition_has_explicit_retrieval_labels(self):
        p=build_plan('How is cooperative learning defined in this article?')
        self.assertEqual(p['expected_labels'],['concept','method'])

    def test_sorting_rule_is_evidence_not_a_generated_answer(self):
        p=build_plan('By what criteria does the algorithm sort detected rectangles?')
        self.assertEqual(p['retrieval_intent'],'sorting_rule_evidence')
        self.assertNotIn('answer',p)

    def test_compound_list_can_retrieve_existing_measurement_evidence(self):
        p=build_plan('What compounds were isolated from Salvia officinalis?')
        self.assertEqual(p['expected_labels'],['concept','metric'])
