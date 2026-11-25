import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_single_frozen_qa import run
from workflow_io import canonical_hash, file_hash
from freeze_native_qa_contexts import evidence_record


class NativeQASafetyTests(unittest.TestCase):
    def test_empty_context_stops_before_credential_access(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            case = {'question_id':1, 'method':'kg_native', 'context':[], 'context_json':'[]',
                    'context_sha256':canonical_hash('[]')}
            contexts = root / 'contexts.jsonl'
            contexts.write_text(json.dumps(case)+'\n', encoding='utf-8')
            (root / 'manifest.json').write_text(json.dumps({'contexts_sha256':file_hash(contexts)}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'No context'):
                asyncio.run(run(contexts, root/'nonexistent_secret', root/'history', root/'output', method='kg_native', execute=True))
            self.assertFalse((root/'output').exists())

    def test_evidence_export_preserves_paper_identity_without_ranking_scores(self):
        item = {'entity_name':'A', 'entity_type':'Method', 'entity_desc':'D',
                'source_paper_keys':['p.json'], 'source_papers':['Title'],
                'connections':[], 'ranking':{'score':0.9}}
        exported = evidence_record(item)
        self.assertEqual(exported['source_paper_keys'], ['p.json'])
        self.assertEqual(exported['entity']['description'], 'D')
        self.assertNotIn('ranking', exported)
