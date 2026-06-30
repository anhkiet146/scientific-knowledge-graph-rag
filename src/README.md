# Source code

This directory contains the main implementation used in the Scientific KG-RAG workflow.

- `extraction/`: PDF preprocessing and LLM-based entity/relation extraction.
- `normalization/`: entity normalization utilities.
- `graph_construction/`: Neo4j graph loading scripts.
- `retrieval/`: graph search, hybrid retrieval, ranking, and answer synthesis.
- `evaluation/`: extraction and QA evaluation utilities.
- `api/`: FastAPI/backend integration files used by the web QA service.

Credentials are not stored in source files. Runtime secrets such as `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `NEO4J_PASSWORD`, and database URIs must be provided through environment variables or local configuration files that are not committed.

