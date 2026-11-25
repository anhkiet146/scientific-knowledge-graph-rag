import ast
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src/extraction"))
from prompt_library import (PROMPT_VERSION,SYSTEM_INSTRUCTION,TEXT,build_user_prompt,repair_prompt,
                            audit_prompt,prompt_hashes)
from reextract_review import validate_extraction,Client,sections_from_document,schema


class ExtractionPromptTests(unittest.TestCase):
    def test_pdf_table_layout_survives_prompt_preparation(self):
        raw="Model       Accuracy\nLearner A   0.91\nLearner B   0.87"
        sections=sections_from_document({"sections":[{"category":"pdf_page","section_title":"Original PDF page 5","content":raw}]})
        self.assertEqual(sections[0]["text"],raw)
        self.assertEqual(sections[0]["kind"],"pdf_page")
        self.assertIn(raw,json.loads(build_user_prompt(sections).split("CURRENT ARTICLE SECTIONS (only evidence source):\n")[1])[0]["text"])

    def test_all_examples_have_valid_quotes_types_and_endpoints(self):
        examples=json.loads(TEXT["extraction_few_shot_examples.json"])["examples"]
        self.assertEqual(len(examples),3)
        for example in examples:
            accepted,issues=validate_extraction(example["expected_output"],example["article_sections"])
            self.assertEqual(issues,[],example["purpose"])
            self.assertEqual(accepted,example["expected_output"])

    def test_author_from_body_is_rejected(self):
        quote={"section_id":"s001","text":"Earlier work by Alice Doe studied this subject."}
        payload={"entities":[{"id":"Alice Doe","type":"Author","description":"author","evidence":[quote]}],"relations":[]}
        accepted,issues=validate_extraction(payload,[{"section_id":"s001","kind":"body","text":quote["text"]}])
        self.assertEqual(accepted["entities"],[])
        self.assertEqual(issues[0]["reason"],"name_not_grounded_in_header")

    def test_batch_and_upload_share_rules(self):
        sections=[{"section_id":"s000","kind":"body","text":"Actual article source."}]
        batch=build_user_prompt(sections)
        upload=build_user_prompt(sections,channel="upload")
        self.assertIn(TEXT["entity_relation_extraction_prompt.md"],batch)
        self.assertIn(TEXT["entity_relation_extraction_prompt.md"],upload)
        self.assertIn(TEXT["web_upload_extraction_prompt.md"],upload)
        self.assertNotIn(TEXT["web_upload_extraction_prompt.md"],batch)
        self.assertEqual(len(prompt_hashes()),6)

    def test_repair_and_audit_placeholders_are_resolved(self):
        repair=repair_prompt("ORIGINAL ARTICLE","BROKEN JSON","malformed_json")
        self.assertIn("ORIGINAL ARTICLE",repair)
        self.assertIn("BROKEN JSON",repair)
        self.assertNotIn("{{",repair)
        audit=audit_prompt([{"text":"evidence"}],{"entities":[],"relations":[]})
        self.assertNotIn("{{",audit)
        self.assertIn("not independent human gold",audit)

    def test_truncated_candidate_is_not_reintroduced_to_repair(self):
        text=repair_prompt("ORIGINAL ARTICLE","CORRUPTED CANDIDATE"+"\\n"*100,"MAX_TOKENS")
        self.assertIn("ORIGINAL ARTICLE",text)
        self.assertNotIn("CORRUPTED CANDIDATE",text)
        self.assertNotIn("\\n"*10,text)

    def test_whitespace_cleanup_preserves_scientific_characters_and_values(self):
        sections=sections_from_document({"title":"Test","sections":[{"content":"Measured 1.2 µg/mL\n\n  and area 3 m²."}]})
        self.assertEqual(sections[-1]["text"],"Measured 1.2 µg/mL and area 3 m².")

    def test_system_rules_are_sent_as_system_instruction(self):
        response={"candidates":[{"finishReason":"STOP","content":{"parts":[{"text":"{}"}]}}]}
        captured=[]
        def request(req,**kwargs):
            captured.append(json.loads(req.data));return io.BytesIO(json.dumps(response).encode())
        with patch("urllib.request.urlopen",side_effect=request),patch("time.sleep"):
            Client("test-secret","gemini-2.5-flash",4).generate("TEST ARTICLE")
        self.assertEqual(captured[0]["systemInstruction"]["parts"][0]["text"],SYSTEM_INSTRUCTION)
        self.assertEqual(captured[0]["contents"][0]["parts"][0]["text"],"TEST ARTICLE")

    def test_upload_has_no_duplicate_inline_prompt(self):
        source=(ROOT/"src/api/web_backend.py").read_text(encoding="utf-8")
        names={target.id for node in ast.parse(source).body if isinstance(node,ast.Assign)
               for target in node.targets if isinstance(target,ast.Name)}
        self.assertNotIn("IMPROVED_INSTRUCTION",names)
        self.assertNotIn("FEW_SHOT_EXAMPLES",names)

    def test_upload_function_uses_shared_system_schema_and_header_validation(self):
        from google.genai import types
        from types import SimpleNamespace
        from src.extraction.strict_runner import SYSTEM,policy
        source=ast.parse((ROOT/"src/api/web_backend.py").read_text(encoding="utf-8"))
        function=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=="extract_knowledge")
        calls=[]
        def generate(**kwargs):
            calls.append(kwargs)
            catalog=json.loads(kwargs['contents'].split('CURRENT ARTICLE:\n')[1])['evidence_catalog']
            identifier=next(r['id'] for r in catalog if 'Author: Alice Doe.' in r['text'])
            payload={"entities":[{"id":"e1","name":"Alice Doe","type":"Author","description":"An author.","evidence_ids":[identifier]}],"relations":[]}
            return SimpleNamespace(text=json.dumps(payload),candidates=[SimpleNamespace(finish_reason='STOP')])
        namespace=dict(sections_from_document=sections_from_document,types=types,
            logger=SimpleNamespace(error=lambda *args:None),
            gemini_client=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
        exec(compile(ast.Module(body=[function],type_ignores=[]),"upload_extract_test","exec"),namespace)
        result=namespace["extract_knowledge"]({"filename":"paper.pdf","title":"Test article",
            "raw_header":"Author: Alice Doe.","abstract":"","sections":[]})
        self.assertEqual(result["extraction_result"]["entities"][0]["name"],"Alice Doe")
        self.assertEqual(calls[0]["config"].system_instruction,SYSTEM)
        self.assertIn('evidence_ids',calls[0]['config'].response_schema['properties']['entities']['items']['properties'])
        self.assertEqual(result['candidate_status'],'pending_semantic_review')
        self.assertNotIn('review',result)


if __name__=="__main__":unittest.main()
