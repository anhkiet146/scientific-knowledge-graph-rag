import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('live_corpus',Path(__file__).resolve().parents[1]/'scripts/compare_live_corpus.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class LiveCorpusTests(unittest.TestCase):
    def test_extensions_and_windows_paths_match_without_merging_papers(self):
        rows,s=m.compare([{'filename':'A.json','title':'Study'}],[{'graph_id':'1','filename':'E:\\docs\\a.pdf'}])
        self.assertEqual(rows[0]['frozen_filename'],'A.json')
        self.assertEqual(s['matched_unique_frozen_papers'],1)

    def test_title_only_match_is_not_accepted_as_identity(self):
        rows,s=m.compare([{'filename':'a.json','title':'Study'}],[{'graph_id':'1','filename':'uploaded.pdf','title':'Study'}])
        self.assertEqual(rows[0]['state'],'title_candidate_needs_review')
        self.assertEqual(s['matched_unique_frozen_papers'],0)

    def test_duplicates_and_missing_frozen_papers_remain_visible(self):
        _,s=m.compare([{'filename':'a.json'},{'filename':'b.json'}],[{'graph_id':'1','filename':'a.pdf'},{'graph_id':'2','filename':'a.json'}])
        self.assertEqual(s['duplicate_live_nodes_for_frozen_filename'],{'a.json':2})
        self.assertEqual(s['missing_frozen_papers'],['b.json'])

    def test_duplicate_element_ids_and_ambiguous_filenames_rejected(self):
        with self.assertRaises(ValueError):m.compare([{'filename':'a.json'},{'filename':'A.pdf'}],[])
        with self.assertRaises(ValueError):m.compare([],[{'graph_id':'1'},{'graph_id':'1'}])


if __name__=='__main__':unittest.main()
