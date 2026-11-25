import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/extraction'))
from coordinate_review import validate_submission


class CoordinateReviewTests(unittest.TestCase):
    def fixture(self):
        return {'purpose':'Development review, not independent gold','manifest_sha256':'a'*64,
            'records':[{'review_id':rid,'job_id':'t1','observation_id':rid,'candidate_sha256':'b'*64,
                'source_pdf_sha256':'c'*64,'review':{'status':'unreviewed','reviewer':'','notes':'',
                    'layout_correct':None,'measurement_correct':None,'footnote_and_reporting_note_checked':None}}
                for rid in ('r1','r2')]}
    def approved(self,template):
        value=copy.deepcopy(template);value['records'][0]['review']={'status':'approved','reviewer':'Synthetic test reviewer',
            'notes':'Synthetic unit test only','layout_correct':True,'measurement_correct':True,'footnote_and_reporting_note_checked':True}
        return value
    def test_blank_and_partial_reviews_never_enable_graph(self):
        template=self.fixture();result=validate_submission(template,template)
        self.assertEqual(result['counts']['unreviewed'],2);self.assertFalse(result['all_records_reviewed'])
        result=validate_submission(template,self.approved(template))
        self.assertEqual(result['counts']['approved'],1);self.assertFalse(result['approved_for_graph'])
        self.assertFalse(result['independent_gold'])
    def test_approval_requires_notes_reviewer_and_all_boolean_checks(self):
        template=self.fixture()
        for field,value in [('notes',''),('reviewer',' '),('layout_correct',False),('measurement_correct',None),('layout_correct',1)]:
            with self.subTest(field=field,value=value):
                submission=self.approved(template);submission['records'][0]['review'][field]=value
                with self.assertRaises(ValueError):validate_submission(template,submission)
    def test_changed_candidate_hash_or_manifest_is_rejected(self):
        template=self.fixture()
        for mutation in ('candidate','manifest'):
            submission=copy.deepcopy(template)
            if mutation=='candidate':submission['records'][0]['candidate_sha256']='d'*64
            else:submission['manifest_sha256']='d'*64
            with self.assertRaises(ValueError):validate_submission(template,submission)
    def test_unknown_duplicate_and_missing_records_are_rejected(self):
        template=self.fixture()
        for mutation in ('unknown','duplicate','missing'):
            submission=copy.deepcopy(template)
            if mutation=='unknown':submission['records'][0]['review_id']='unknown'
            elif mutation=='duplicate':submission['records'][1]=submission['records'][0]
            else:submission['records'].pop()
            with self.assertRaises(ValueError):validate_submission(template,submission)
    def test_blocked_candidate_cannot_be_approved(self):
        template=self.fixture()
        with self.assertRaises(ValueError):validate_submission(template,self.approved(template),blocked_ids={'r1'})
    def test_reordered_records_keep_exact_identity(self):
        template=self.fixture();submission=self.approved(template);submission['records'].reverse()
        self.assertEqual(validate_submission(template,submission)['counts']['approved'],1)
