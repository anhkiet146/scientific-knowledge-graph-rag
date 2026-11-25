import importlib.util, unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("triage",Path(__file__).resolve().parents[1]/"scripts/audit_extraction_semantics.py")
triage=importlib.util.module_from_spec(spec);spec.loader.exec_module(triage)

class TriageTests(unittest.TestCase):
    def test_biological_target_and_superficial_alias_are_reviewed_without_mutation(self):
        payload={"entities":[{"id":"MobileNetV3-Small","type":"Method"},{"id":"MobileNetV3 Small","type":"Method"},{"id":"Bacillus cereus","type":"Dataset"}],"relations":[{"source":"MobileNetV3-Small","type":"EVALUATED_ON","target":"Bacillus cereus"}]}
        result=triage.audit(payload)
        self.assertEqual(len(result["issues"]),3)
        self.assertEqual(len(payload["entities"]),3)
        self.assertEqual(result["semantic_correctness"],"not_established")
    def test_family_and_variant_are_not_alias_candidates(self):
        result=triage.audit({"entities":[{"id":"MobileNet","type":"Method"},{"id":"MobileNetV3-Small","type":"Method"}],"relations":[]})
        self.assertEqual(result["issues"],[])
