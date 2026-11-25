import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from regrade_legacy_qa import prepare,validate


class LegacyRegradingTests(unittest.TestCase):
    def row(self):
        return dict(question='What is the measured value?',reference_answer='12',generated_answer='12',
                    retrieved_context=json.dumps([{'content':'Measured value: 12.'}]),
                    method='SECRET_METHOD',faithfulness=.999,judge_model='SECRET_OLD_JUDGE')

    def grade(self):
        return dict(faithfulness=1,relevancy=1,context_precision=1,context_recall=1,
            unsupported_answer=False,controlled_refusal=False,reference_concern=False,
            rationale='Supported by the supplied value.',evidence_quotes=['Measured value: 12.'])

    def test_old_method_and_scores_are_not_sent(self):
        prompt,_=prepare(self.row())
        for value in ('SECRET_METHOD','SECRET_OLD_JUDGE','0.999'):self.assertNotIn(value,prompt)

    def test_missing_evidence_requires_null_scores_and_truncation_rejected(self):
        row=self.row();row['retrieved_context']='[]'
        _,context=prepare(row)
        with self.assertRaises(ValueError):validate(json.dumps(self.grade()),context)
        grade=self.grade();grade.update(faithfulness=None,context_precision=None,context_recall=None,evidence_quotes=[])
        self.assertIsNone(validate(json.dumps(grade),context)['faithfulness'])
        row=self.row();row['generated_answer']='x'*65000
        with self.assertRaises(ValueError):prepare(row)

    def test_out_of_range_boolean_score_and_invented_quotes_rejected(self):
        _,context=prepare(self.row())
        self.assertEqual(validate(json.dumps(self.grade()),context)['faithfulness'],1)
        for field,value in [('faithfulness',True),('context_recall',1.1),('evidence_quotes',['Invented evidence'])]:
            grade=self.grade();grade[field]=value
            with self.assertRaises(ValueError):validate(json.dumps(grade),context)


if __name__=='__main__':unittest.main()
