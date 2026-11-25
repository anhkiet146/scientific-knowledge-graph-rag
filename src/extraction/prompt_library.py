"""Shared, versioned extraction prompts for batch and upload workflows."""
import hashlib
import json
from pathlib import Path

PROMPT_VERSION="review-extraction-v2.3"
PROMPT_DIR=Path(__file__).resolve().parents[2]/"prompts"
FILES=("extraction_system_prompt.md","entity_relation_extraction_prompt.md",
       "extraction_few_shot_examples.json","extraction_repair_prompt.md",
       "extraction_audit_prompt.md","web_upload_extraction_prompt.md")
TEXT={name:(PROMPT_DIR/name).read_text(encoding="utf-8") for name in FILES}
SYSTEM_INSTRUCTION=TEXT["extraction_system_prompt.md"]
USER_PREFIX=TEXT["entity_relation_extraction_prompt.md"]+"\n\nSYNTHETIC CALIBRATION EXAMPLES:\n"+TEXT["extraction_few_shot_examples.json"]


def prompt_hashes():
    return {name:hashlib.sha256(text.encode()).hexdigest() for name,text in TEXT.items()}


def build_user_prompt(sections,channel="batch"):
    if channel not in {"batch","upload"}:raise ValueError("Unknown extraction channel")
    extra="\n\n"+TEXT["web_upload_extraction_prompt.md"] if channel=="upload" else ""
    return USER_PREFIX+extra+"\n\nCURRENT ARTICLE SECTIONS (only evidence source):\n"+json.dumps(sections,ensure_ascii=False)


def repair_prompt(original_prompt,previous_candidate,failure):
    if "MAX_TOKENS" in str(failure) or "\\n"*10 in previous_candidate:
        previous_candidate="Previous candidate omitted because it was truncated or repetitive. Re-extract from the original article."
    note=TEXT["extraction_repair_prompt.md"].replace("{{validation_failure}}",str(failure)).replace("{{previous_candidate}}",previous_candidate[:12000])
    return original_prompt+"\n\n"+note


def audit_prompt(sections,candidate):
    return TEXT["extraction_audit_prompt.md"].replace("{{article_sections}}",json.dumps(sections,ensure_ascii=False)).replace("{{candidate_extraction}}",json.dumps(candidate,ensure_ascii=False))
