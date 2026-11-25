from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/retrieval'))
import hybrid_retrieval as h
from paper_scope import PaperScope


class NativePaperScopeTests(unittest.TestCase):
    def test_unique_long_title_anchor_without_answer_labels(self):
        scoper = PaperScope({'a':'Effects of uniconazole on mango', 'b':'Analysis of chemicals'})
        self.assertEqual(scoper.select('uniconazole mango authors', named_entities=['Uniconazole'])['allowed_papers'], ['a'])
        self.assertIsNone(scoper.select('chemicals')['allowed_papers'])
        self.assertIsNone(scoper.select('supplemented', named_entities=['EWH30'])['allowed_papers'])

    def test_shared_long_token_alone_does_not_scope(self):
        scoper = PaperScope({'a':'Uniconazole on mango', 'b':'Uniconazole on rice'})
        self.assertIsNone(scoper.select('uniconazole')['allowed_papers'])

    def test_entity_dictionary_distinguishes_name_from_generic_title_word(self):
        scoper = PaperScope({'a':'Effects of uniconazole', 'b':'Supplemented bread'}, entity_names=['Uniconazole (UCZ)'])
        self.assertEqual(scoper.select('authors uniconazole')['allowed_papers'], ['a'])
        self.assertIsNone(scoper.select('supplemented EWH30')['allowed_papers'])

    def test_numeric_measurement_and_partial_name_do_not_create_single_anchor(self):
        scoper = PaperScope({'a':'Genetic similarity', 'b':'Detecting crowds'}, entity_names=['Similarity (100%)'])
        self.assertIsNone(scoper.select('similarity')['allowed_papers'])
        self.assertIsNone(scoper.select('detecting', named_entities=['Detecting groups'])['allowed_papers'])

    def test_empty_scope_is_not_unrestricted(self):
        with patch.object(h, '_fulltext_anchors', return_value=[]) as full, patch.object(h, '_lexical_anchors', return_value=[]) as lexical, patch.object(h, '_expand_anchors', return_value=[]) as expand:
            _, diagnostic = h.retrieve_candidates(Mock(), 'question', {'search_terms':['term']}, allowed_papers=[])
            self.assertEqual(diagnostic['allowed_papers'], [])
            for fn in (full, lexical, expand):
                self.assertEqual(fn.call_args.kwargs['allowed_papers'], [])

    def test_invalid_scope_rejected_before_query(self):
        with patch.object(h, '_fulltext_anchors') as full:
            for value in ['paper.json', [None], ['']]:
                with self.assertRaises(ValueError):
                    h.retrieve_candidates(Mock(), 'question', {}, allowed_papers=value)
            full.assert_not_called()

    def test_scope_deduplicated_for_each_stage(self):
        with patch.object(h, '_fulltext_anchors', return_value=[]) as full, patch.object(h, '_lexical_anchors', return_value=[]) as lexical, patch.object(h, '_expand_anchors', return_value=[]) as expand:
            h.retrieve_candidates(Mock(), 'question', {}, allowed_papers=['b','a','a'])
            for fn in (full, lexical, expand):
                self.assertEqual(fn.call_args.kwargs['allowed_papers'], ['a','b'])
