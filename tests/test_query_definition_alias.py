import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/retrieval'))
from hybrid_retrieval import build_query_plan, _entity_match


class DefinitionAliasTests(unittest.TestCase):
    def test_explicit_bilingual_definition_matches_either_name(self):
        plan = build_query_plan('Lesson study (Nghiên cứu bài học) được định nghĩa như thế nào?')
        self.assertEqual(len(plan['query_alias_groups']), 1)
        self.assertEqual(_entity_match(plan, {'entity_name':'Lesson Study'}), 1)
        self.assertEqual(_entity_match(plan, {'entity_name':'Unrelated lesson planning'}), 0)

    def test_no_equivalence_inferred_for_experimental_condition(self):
        plan = build_query_plan('Daily gain (EWH30) đạt bao nhiêu?')
        self.assertEqual(plan['query_alias_groups'], [])

    def test_alias_matches_complete_phrase(self):
        plan = {'entities':['Study'], 'query_alias_groups':[['Study','Bài học']]}
        self.assertEqual(_entity_match(plan, {'entity_name':'Studying'}), 0)
