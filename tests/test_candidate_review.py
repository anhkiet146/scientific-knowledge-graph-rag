import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
import test_chunk_execution as fixture_helpers

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('candidate_review_script',ROOT/'scripts/prepare_chunk_candidate_review.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
from chunk_runner import run
from workflow_io import atomic_json,read_json


class CandidateReviewTests(unittest.TestCase):
    def fixture(self,base):
        helper=fixture_helpers.ChunkExecutionTests();helper.setUp()
        args,key=helper.fixtures(base);args.max_tasks=0
        return args,key

    def test_unresolved_citation_is_preserved_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            args,key=self.fixture(Path(tmp));path=args.offline_responses/key/'metadata.json'
            fixture=read_json(path);payload=json.loads(fixture['text'])
            payload['entities'][0]['evidence_ids']=['unknown-source-id']
            fixture['text']=json.dumps(payload);atomic_json(path,fixture);run(args)
            pack=module.prepare(args.output)
            self.assertEqual(pack['reviewed_record_count'],0)
            self.assertEqual(pack['records'][0]['cited_source'],[{'unresolved_evidence_id':'unknown-source-id'}])
            self.assertEqual(pack['records'][0]['review']['status'],'unreviewed')

    def test_truncated_json_does_not_prevent_remaining_task_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            args,key=self.fixture(Path(tmp));path=args.offline_responses/key/'metadata.json'
            atomic_json(path,{'text':'{"entities":[','finish_reason':'MAX_TOKENS'});run(args)
            pack=module.prepare(args.output)
            self.assertEqual(len(pack['unparseable_tasks']),1)
            self.assertEqual(pack['unparseable_tasks'][0]['task_id'],'metadata')
            self.assertEqual(pack['reviewed_record_count'],0)
