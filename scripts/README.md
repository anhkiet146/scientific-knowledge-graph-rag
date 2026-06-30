# Pipeline scripts

This directory contains the main runnable scripts for reproducing the KG construction pipeline:

1. `preprocess_pdf.py` - parse PDF files and recover structured article text.
2. `extract_entities.py` - run LLM-based entity and relation extraction.
3. `normalize_entities.py` - normalize extracted entity names and graph records.
4. `build_graph.py` - load normalized graph JSON files into Neo4j.

Evaluation and baseline-comparison utilities are kept under `src/evaluation/` because they are analysis utilities rather than the core data-construction pipeline.

