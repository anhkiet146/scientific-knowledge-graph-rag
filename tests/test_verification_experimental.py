import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src/retrieval'))
from claim_verification import REFUSAL
from claim_verification_experimental import filter_claims_experimental, content_values


def check(draft, quote, context=None):
    claim = {'text': draft, 'quote': quote, 'context_index': 0, 'supported': True, 'atomic': True}
    return filter_claims_experimental(draft, [context if context is not None else {'text': quote}], {'claims': [claim]})


class ExperimentalVerificationTests(unittest.TestCase):
    def test_changed_number_and_sign_are_rejected(self):
        for draft, quote in [('Model A scored 90 percent.', 'Model A scored 80 percent.'),
                             ('The change was -70 percent.', 'The change was +70 percent.')]:
            answer, audit = check(draft, quote)
            self.assertEqual(answer, REFUSAL)
            self.assertIn('numeric_token_or_sign_not_in_quote', audit[0]['reasons'])

    def test_metadata_cannot_supply_quote(self):
        for key in ['paper_id', 'source_file', 'title', 'unknown']:
            self.assertEqual(check('Trial supported the claim.', 'Trial supported the claim.', {key: 'Trial supported the claim.'})[0], REFUSAL)

    def test_entity_relation_and_passage_content_are_supported(self):
        for context in [{'entity': {'id': 'Phan Van Ut'}}, {'relation': {'source': 'Phan Van Ut'}}, {'author': 'Phan Van Ut'}]:
            self.assertNotEqual(check('Phan Van Ut', 'Phan Van Ut', context)[0], REFUSAL)
        self.assertNotEqual(check('Model A scored 80 percent.', 'Model A scored 80 percent.')[0], REFUSAL)

    def test_unicode_minus_and_extra_quote_numbers(self):
        self.assertNotEqual(check('Change was −70 percent.', 'Change was -70 percent, from 100 percent.')[0], REFUSAL)

    def test_numeric_conversion_is_deliberately_not_inferred(self):
        self.assertEqual(check('Yield was 80.0 percent.', 'Yield was 80 percent.')[0], REFUSAL)

    def test_wrong_object_remains_a_known_limit(self):
        answer, audit = check('Model B scored 80 percent.', 'Model A scored 80 percent.')
        self.assertNotEqual(answer, REFUSAL)
        self.assertFalse(audit[0]['entailment_independently_established'])

    def test_content_allowlist_does_not_recurse_into_metadata(self):
        self.assertEqual(content_values({'metadata': {'text': 'not scientific evidence'}}), [])


if __name__ == '__main__':
    unittest.main()
