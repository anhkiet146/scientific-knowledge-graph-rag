import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/extraction'))
from chunk_runner import prompt_for


class ChunkPromptScopeTests(unittest.TestCase):
    def test_only_metadata_for_evidence_sections_is_sent(self):
        task={'task_id':'body1','scope_ids':['e1'],'context_ids':['e2']}
        catalog={'sections_sha256':'hash','items':[
            {'id':'e1','section_id':'s1','kind':'body','text':'Body'},
            {'id':'e2','section_id':'s2','kind':'header','text':'Author'},
            {'id':'e3','section_id':'s3','kind':'body','text':'Unrelated'}]}
        sections=[{'section_id':f's{i}','page':i,'text':'Text'} for i in range(1,4)]
        payload=json.loads(prompt_for(task,catalog,sections,12).split('\nCURRENT TASK:\n')[1])
        self.assertEqual({s['section_id'] for s in payload['section_metadata']},{'s1','s2'})
        self.assertEqual([e['id'] for e in payload['evidence_catalog']],['e1','e2'])
        self.assertEqual(payload['eligible_header_evidence_ids'],['e2'])
