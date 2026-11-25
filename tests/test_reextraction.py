import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src/extraction"))
from reextract_review import sections_from_document,validate_extraction


class ReextractionTests(unittest.TestCase):
    def test_short_source_sections_are_retained_and_references_excluded(self):
        sections=sections_from_document({"title":"Example","raw_header":"Alice University",
            "sections":[{"category":"discussion","content":"A short but important result."},
                        {"category":"references","content":"An unrelated cited article."}]})
        text=" ".join(s["text"] for s in sections)
        self.assertIn("A short but important result.",text)
        self.assertNotIn("An unrelated cited article.",text)

    def test_ungrounded_entities_and_their_relations_are_rejected(self):
        quote={"section_id":"s000","text":"Method A investigates disease B."}
        sections=[{"section_id":"s000","text":quote["text"]}]
        payload={"entities":[{"id":"Method A","type":"Method","description":"Applied method","evidence":[quote]},
            {"id":"disease B","type":"Concept","description":"Object","evidence":[{"section_id":"s000","text":"fabricated quote"}]}],
            "relations":[{"source":"Method A","type":"USED_FOR","target":"disease B","evidence":[quote]}]}
        accepted,issues=validate_extraction(payload,sections)
        self.assertEqual(len(accepted["entities"]),1)
        self.assertEqual(accepted["relations"],[])
        self.assertEqual({i["reason"] for i in issues},{"no_grounded_source_quote","missing_or_ambiguous_endpoint"})

    def test_valid_quotes_do_not_override_wrong_relation_direction(self):
        quote={"section_id":"s000","text":"Method A investigates disease B."}
        sections=[{"section_id":"s000","text":quote["text"]}]
        payload={"entities":[{"id":"Method A","type":"Method","evidence":[quote]},
                             {"id":"disease B","type":"Concept","evidence":[quote]}],
                 "relations":[{"source":"disease B","target":"Method A","type":"USED_FOR","evidence":[quote]}]}
        accepted,issues=validate_extraction(payload,sections)
        self.assertEqual(len(accepted["entities"]),2)
        self.assertEqual(accepted["relations"],[])
        self.assertEqual(issues[0]["reason"],"invalid_type_signature")


if __name__=="__main__":unittest.main()
