import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from prepare_review_dataset import verify
from repair_relation_fields import repair_payload


class FrozenDatasetTests(unittest.TestCase):
    def test_only_evidenced_field_swaps_are_repaired(self):
        payload={"entities":[{"id":"A"},{"id":"B"}],"relations":[
            {"source":"A","type":"B","target":"USED_FOR"},
            {"source":"A","type":"unknown entity","target":"USED_FOR"}]}
        changes,unresolved=repair_payload(payload)
        self.assertEqual(payload["relations"][0],{"source":"A","type":"USED_FOR","target":"B"})
        self.assertEqual(len(changes),1)
        self.assertEqual(len(unresolved),1)
        self.assertEqual(payload["relations"][1]["type"],"unknown entity")

    def test_modified_or_added_files_are_rejected(self):
        scratch=(ROOT/"work/test-temp").resolve();scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root=Path(folder).resolve();self.assertTrue(root.is_relative_to(scratch))
            for name in ("corpus","extracted","normalized_exact"):(root/name).mkdir()
            path=root/"corpus/paper.json";path.write_text("{}",encoding="utf-8")
            manifest={"files":[{"path":"corpus/paper.json","sha256":hashlib.sha256(path.read_bytes()).hexdigest()}]}
            (root/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
            verify(root)
            path.write_text('{"changed":true}',encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"modified"):verify(root)
            path.write_text("{}",encoding="utf-8")
            (root/"extracted/extra.json").write_text("{}",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"Added/removed"):verify(root)


if __name__=="__main__":unittest.main()
