import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/retrieval'))
from claim_verification import REFUSAL
from claim_verification_literal import filter_claims_literal
from verifier_policies import verifier_policy


def check(draft,source,quote=None):
    verdict={'claims':[dict(text=draft,quote=source if quote is None else quote,
                           context_index=0,supported=True,atomic=True)]}
    return filter_claims_literal(draft,[{'text':source}],verdict)


class LiteralVerificationTests(unittest.TestCase):
    def test_correct_entire_value_kept(self):
        answer,audit=check('Model A scored 80 percent.','Model A scored 80 percent.')
        self.assertNotEqual(answer,REFUSAL)
        self.assertFalse(audit[0]['semantic_entailment_proven'])
        self.assertFalse(audit[0]['source_pdf_verified'])

    def test_wrong_object_negation_unit_and_condition_blocked(self):
        pairs=[
            ('Model B scored 80 percent.','Model A scored 80 percent.'),
            ('Model A increased yield.','Model A did not increase yield.'),
            ('The concentration was 80 mg.','The concentration was 80 g.'),
            ('Model A scored 80 percent on Dataset B.','Model A scored 80 percent on Dataset A.'),
        ]
        for draft,source in pairs:
            with self.subTest(draft=draft):
                self.assertEqual(check(draft,source)[0],REFUSAL)

    def test_fragment_below_negation_cannot_be_selected(self):
        self.assertEqual(check('Model A increased yield.',
                               'It is false that Model A increased yield.',
                               'Model A increased yield.')[0],REFUSAL)

    def test_paraphrase_rejected_and_not_silently_rewritten(self):
        self.assertEqual(check('Model A obtained 80 percent.','Model A scored 80 percent.')[0],REFUSAL)

    def test_compound_list_needs_separate_source_values(self):
        value='Model A scored 80 percent; Model B scored 90 percent.'
        self.assertEqual(check(value,value)[0],REFUSAL)

    def test_whitespace_difference_does_not_remove_conditions(self):
        self.assertNotEqual(check('Model A scored 80 percent.','Model A\nscored 80 percent.')[0],REFUSAL)

    def test_source_case_and_internal_punctuation_preserved(self):
        self.assertEqual(check('Model A-B scored 80 percent.','Model AB scored 80 percent.')[0],REFUSAL)

    def test_terminal_scientific_sign_not_discarded(self):
        self.assertEqual(check('The value is 5!','The value is 5')[0],REFUSAL)
        answer,_=check('The value is 5!','The value is 5!')
        self.assertIn('5!',answer)

    def test_verdict_cannot_append_punctuation_missing_from_draft(self):
        verdict={'claims':[dict(text='Phan Van Ut.',quote='Phan Van Ut.',
                               context_index=0,supported=True,atomic=True)]}
        self.assertEqual(filter_claims_literal('Phan Van Ut',[{'author':'Phan Van Ut.'}],verdict)[0],REFUSAL)

    def test_empty_and_invalid_verdicts_do_not_create_answer(self):
        self.assertEqual(filter_claims_literal('Anything',[],{'claims':[]})[0],REFUSAL)
        with self.assertRaises(ValueError):
            filter_claims_literal('Anything',[],{'claims':{}})

    def test_new_policy_is_explicit_and_legacy_policies_retained(self):
        self.assertIs(verifier_policy('verbatim_value')[1],filter_claims_literal)
        for name in ['v1','v2','content_numeric']:
            self.assertTrue(callable(verifier_policy(name)[1]))
        with self.assertRaises(ValueError):
            verifier_policy('unregistered')
