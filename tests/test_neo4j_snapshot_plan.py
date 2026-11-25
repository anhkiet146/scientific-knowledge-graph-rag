import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_neo4j_snapshot import build_records


class SnapshotPlanTests(unittest.TestCase):
    def setUp(self):
        self.graph = {'nodes': [{'id': 'p:e0', 'source_occurrences': [
            {'paper': 'p', 'type': 'Author', 'name': 'A', 'source_entity': {'description': 'D'}}]}],
            'edges': [{'source': 'p:e0', 'target': 'p:e0', 'paper': 'p', 'type': 'RELATED_TO'}]}

    def test_preserves_provenance_without_approval(self):
        before = copy.deepcopy(self.graph)
        result = build_records(self.graph, {'p': {'key': 'p'}})
        self.assertEqual(self.graph, before)
        self.assertEqual(result['mentions'], [{'paper': 'p', 'entity': 'p:e0'}])
        self.assertFalse(result['relations'][0]['production_approved'])

    def test_rejects_dangling_endpoint(self):
        self.graph['edges'][0]['target'] = 'missing'
        with self.assertRaises(ValueError): build_records(self.graph, {'p': {}})

    def test_rejects_unknown_paper(self):
        with self.assertRaises(ValueError): build_records(self.graph, {})

    def test_rejects_duplicate_identity(self):
        self.graph['nodes'] *= 2
        with self.assertRaises(ValueError): build_records(self.graph, {'p': {}})

    def test_rejects_cypher_type_injection(self):
        self.graph['edges'][0]['type'] = 'X` DELETE n'
        with self.assertRaises(ValueError): build_records(self.graph, {'p': {}})
