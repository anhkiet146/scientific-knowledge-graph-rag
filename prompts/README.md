# Prompt templates

This directory contains the main English prompt templates used by the Scientific KG-RAG system.

The prompts are grouped by task:

- `entity_relation_extraction_prompt.md`: extraction of entities and relations from scientific articles.
- `web_upload_extraction_prompt.md`: extraction prompt used by the upload/API workflow.
- `kg_rag_intent_detection_prompt.md`: routing between graph-domain and general requests.
- `kg_rag_query_analysis_prompt.md`: structured query analysis for graph retrieval.
- `kg_rag_answer_synthesis_prompt.md`: final KG-grounded answer generation.
- `kg_rag_general_answer_prompt.md`: controlled response for non-domain/general requests.
- `kg_rag_followup_suggestions_prompt.md`: follow-up question generation.
- `baseline_answer_synthesis_prompt_function.md`: answer prompt used by BM25/Vector baselines.
- `query_translation_prompt_function.md`: Vietnamese-to-English query translation for retrieval.
- `rag_evaluation_judge_prompt_function.md`: automated RAG evaluation rubric.
- `annotation_judge_prompt.md`: prompt for creating/checking extraction annotations.

Notes:

- Runtime credentials are not included.
- The templates are written in English for repository publication and reproducibility.
- Some implementation files may still contain Vietnamese UI messages or comments from the original application.


## Active extraction prompts: review-extraction-v2.3

Batch and upload now load their extraction prompts from the same files through `src/extraction/prompt_library.py`:

- `extraction_system_prompt.md`: scope, source-only behavior, injection resistance and JSON-only output.
- `entity_relation_extraction_prompt.md`: seven entity types, five directed signatures, current-study attribution, numeric conditions, exact quotes and abstention.
- `extraction_few_shot_examples.json`: three fictional, cross-domain examples with positive and negative cases. These are NOT benchmark annotations.
- `web_upload_extraction_prompt.md`: upload-specific rules; shared batch rules still apply.
- `extraction_repair_prompt.md`: a second-attempt repair prompt used only after a failed response, not for every document.
- `extraction_audit_prompt.md`: optional semantic audit. It is not called automatically and does not create independent gold labels.

The batch runner uses a system instruction plus a structured user input containing section ids/kinds. Author/Institution records must have header-grounded names; affiliations need header evidence. Source snapshots, exact per-request prompts, model metadata, validation issues, and all prompt hashes are saved. Updating a prompt requires a new output directory.

A normal extraction still uses one model call per article. A repair can add a second call for a failed response. An optional model audit would add a separate call per article; do not claim it is free or independent human evaluation. A correct JSON structure and a real quote do not guarantee semantic correctness; validate on a held-out, independently checked set.

The eight documents saved under the earlier prompt remain an earlier-version experiment. Do not merge them silently into the new prompt version's 482-document run.

The v2.1 serialization refinement collapses input whitespace without changing scientific characters/values, uses compact single-line JSON strings, and omits a truncated/repetitive candidate from repair feedback. This addresses observed newline-escape loops; it does not guarantee accuracy or complete extraction.

The v2.2 active protocol is configs/review_protocol_v1.json. Human annotation guidance is docs/ANNOTATION_GUIDELINES_VI.md. The legacy annotation judge prompt and evaluate_with_judge.py are not independent gold and must not replace double human annotation. PDF-page sections preserve layout; metadata sections collapse whitespace.

Active continuation: review-extraction-v2.3 / configs/review_protocol_v1_1.json. Lines with U+FFFD are excluded from quoteable PDF fragments; original sources remain unchanged. The two-paper live pilot FAILED semantic acceptance; do not interpret complete receipts as scientific approval. evidence_id_transport_prototype.md is OFFLINE ONLY and is not wired into the active runner. See outputs/review_continuation_2026-11-13/pilot_verdict.json in the working artifacts.
