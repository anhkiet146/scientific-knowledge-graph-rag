import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ranking_sensitivity import validate_candidates
from hybrid_retrieval import _relation_match

class RankingSensitivityTests(unittest.TestCase):
    def test_untyped_connections_block_analysis(self):
        with self.assertRaises(ValueError):validate_candidates([{'candidates':[{'connections':[{'related_name':'Target'}]}]}])

    def test_typed_connections_are_scored(self):
        item={'connections':[{'relation':'USED_FOR','related_name':'Target'}]}
        validate_candidates([{'candidates':[item]}])
        self.assertEqual(_relation_match({'relations':['USED_FOR']},item),1)
        self.assertEqual(_relation_match({'relations':['AFFILIATED_WITH']},item),0)

    def test_isolated_nodes_remain_valid(self):
        validate_candidates([{'candidates':[{'connections':[]}]}])
