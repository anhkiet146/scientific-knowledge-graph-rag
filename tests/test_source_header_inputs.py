import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_source_headers import attach_header


class SourceHeaderInputTests(unittest.TestCase):
    def setUp(self):
        self.text='Academic Editor: Other Person\nArticle Title\nAlice Doe\nExample University\nAbstract: Body text.'
        self.document={'title':'Article Title','sections':[{'page':1,'content':self.text}]}
        self.decision={'start':self.text.index('Article Title'),'end':self.text.index('Abstract:'),
            'source_sha256':'source','review_status':'assistant_visual_source_check_not_independent'}

    def test_source_copy_is_unchanged_and_editor_excluded(self):
        before=copy.deepcopy(self.document);result=attach_header(self.document,self.decision)
        self.assertEqual(self.document,before)
        self.assertNotIn('Academic Editor',result['raw_header'])
        self.assertEqual(result['raw_header'],self.text[self.decision['start']:self.decision['end']])

    def test_editor_cannot_be_promoted_to_author_header(self):
        self.decision['start']=0
        with self.assertRaises(ValueError):attach_header(self.document,self.decision)

    def test_existing_header_not_overwritten(self):
        self.document['raw_header']='Existing header'
        with self.assertRaises(ValueError):attach_header(self.document,self.decision)

    def test_unreviewed_header_rejected(self):
        self.decision['review_status']='unreviewed'
        with self.assertRaises(ValueError):attach_header(self.document,self.decision)

    def test_boolean_span_rejected(self):
        self.decision['start']=False
        with self.assertRaises(ValueError):attach_header(self.document,self.decision)

    def test_missing_title_can_only_come_from_literal_header_span(self):
        self.document['title']='';start=self.decision['start'];self.decision['title_span']=[start,start+len('Article Title')]
        result=attach_header(self.document,self.decision)
        self.assertEqual(result['title'],'Article Title')
