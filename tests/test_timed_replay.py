import copy
import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('timed_replay',SCRIPTS/'audit_timed_replay.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def row():
    return {'question_id':1,'method':'bm25','question':'Q','shared_query':'Q','context_json':'[]',
        'context_sha256':'hash','context_tokens':0,'paper_scope':[],
        'timing':{'source_selection_seconds':.1,'search_seconds':.2,'query_embedding_seconds':0,
            'packing_seconds':.3,'retrieval_stage_sum_seconds':.6}}


class ReplayTests(unittest.TestCase):
    def test_unchanged_context_and_additive_stages(self):
        self.assertEqual(module.compare([row()],[row()]),1)

    def test_changed_context_rejected(self):
        changed=row();changed['context_json']='changed'
        with self.assertRaises(ValueError):module.compare([row()],[changed])

    def test_nonfinite_negative_and_nonadditive_rejected(self):
        for value in [float('nan'),-1,False,1]:
            changed=row();changed['timing']['retrieval_stage_sum_seconds']=value
            with self.assertRaises(ValueError):module.validate_timing(changed)

    def test_missing_or_duplicate_grid_rejected(self):
        for changed in [[],[row(),copy.deepcopy(row())]]:
            with self.assertRaises(ValueError):module.compare([row()],changed)


if __name__=='__main__':unittest.main()
