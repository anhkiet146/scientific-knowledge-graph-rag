from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/evaluation'))
import judge_existing_results as judge


class JudgeProvenanceTests(unittest.TestCase):
    def test_metadata_uses_returned_model_and_actual_parameters(self):
        response=types.SimpleNamespace(status='completed',model='gpt-snapshot-synthetic',id='resp_test',output_text='{}')
        create=Mock(return_value=response)
        client=types.SimpleNamespace(responses=types.SimpleNamespace(create=create))
        module=types.SimpleNamespace(OpenAI=Mock(return_value=client))
        with patch.dict(sys.modules,{'openai':module}),patch.object(judge,'parse_judge_output',return_value={}):
            result=judge.judge_answer_openai('q','r','a',[],'gpt-requested')
        self.assertEqual(result['judge_model_used'],'gpt-snapshot-synthetic')
        self.assertEqual(result['judge_model_requested'],'gpt-requested')
        self.assertNotIn('temperature',create.call_args.kwargs)
        self.assertFalse(create.call_args.kwargs['store'])

    def test_incomplete_response_is_rejected(self):
        client=types.SimpleNamespace(responses=types.SimpleNamespace(create=Mock(return_value=
            types.SimpleNamespace(status='incomplete',model='synthetic'))))
        with patch.dict(sys.modules,{'openai':types.SimpleNamespace(OpenAI=lambda:client)}):
            with self.assertRaises(ValueError):judge.judge_answer_openai('q','r','a',[],'gpt-requested')


if __name__=='__main__':unittest.main()
