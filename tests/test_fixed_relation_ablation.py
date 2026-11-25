from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from compare_normalization_retrieval import relation_tracks


class FixedRelationAblationTests(unittest.TestCase):
    def test_same_source_records_for_all_fixed_relation_tracks(self):
        original=[{'edge':'original'}];checked=[{'edge':'source_checked'}]
        tracks=relation_tracks(original,checked,True,'fixed_source_checked')
        self.assertEqual(len(tracks),6)
        self.assertTrue(all(relations is checked for _,relations in tracks))

    def test_historical_composite_comparison_stays_reproducible(self):
        original=[{'edge':'original'}];checked=[{'edge':'source_checked'}]
        tracks=dict(relation_tracks(original,checked))
        self.assertIs(tracks['raw'],original)
        self.assertIs(tracks['pdf_alias_source_checked'],checked)

    def test_unknown_relation_policy_rejected(self):
        with self.assertRaises(ValueError):relation_tracks([],[],relation_policy='silent_repair')
