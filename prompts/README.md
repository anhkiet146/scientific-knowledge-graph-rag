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

