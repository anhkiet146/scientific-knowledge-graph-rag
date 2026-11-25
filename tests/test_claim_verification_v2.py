import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/retrieval'))
from claim_verification import filter_claims_v2,REFUSAL


class VerificationV2Tests(unittest.TestCase):
    def run_claim(self,text='Phan Van Ut',quote='Phan Van Ut',context=None,**extra):
        claim=dict(text=text,quote=quote,context_index=0,supported=True,atomic=True)
        claim.update(extra)
        return filter_claims_v2('Phan Van Ut [1]',[context or {'author':'Phan Van Ut'}],{'claims':[claim]})

    def test_short_exact_author_leaf_and_terminal_period(self):
        answer,audit=self.run_claim(text='Phan Van Ut.')
        self.assertNotEqual(answer,REFUSAL)
        self.assertEqual(audit[0]['matched_draft_span'],'Phan Van Ut')

    def test_no_substring_of_different_word(self):
        self.assertEqual(self.run_claim(text='Van U')[0],REFUSAL)

    def test_json_key_is_not_source_evidence(self):
        self.assertEqual(self.run_claim(context={'Phan Van Ut':'unknown'})[0],REFUSAL)

    def test_short_number_does_not_pass(self):
        answer,_=filter_claims_v2('70',[{'value':'70'}],{'claims':[dict(text='70',quote='70',context_index=0,supported=True,atomic=True)]})
        self.assertEqual(answer,REFUSAL)

    def test_atomicity_is_required(self):
        self.assertEqual(self.run_claim(atomic=False)[0],REFUSAL)

    def test_duplicates_are_explicitly_rejected(self):
        claim=dict(text='Phan Van Ut',quote='Phan Van Ut',context_index=0,supported=True,atomic=True)
        answer,audit=filter_claims_v2('Phan Van Ut',[{'name':'Phan Van Ut'}],{'claims':[claim,claim]})
        self.assertEqual(len(answer.splitlines()),1)
        self.assertIn('duplicate_claim',audit[1]['reasons'])

    def test_signs_and_numbers_are_not_normalized_away(self):
        claim=dict(text='Accuracy -70%',quote='Accuracy +70%',context_index=0,supported=True,atomic=True)
        self.assertEqual(filter_claims_v2('Accuracy +70%',[{'text':'Accuracy +70%'}],{'claims':[claim]})[0],REFUSAL)

    def test_boolean_index_rejected(self):
        self.assertEqual(self.run_claim(context_index=True)[0],REFUSAL)

    def test_untrusted_missing_fields_fail_closed(self):
        self.assertEqual(filter_claims_v2('Answer',[],{'claims':[None,{}]})[0],REFUSAL)
