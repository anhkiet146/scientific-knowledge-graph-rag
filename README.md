# Scientific Knowledge Graph RAG

This repository contains the source code, derived data, prompts, schemas, and evaluation outputs for a scientific question-answering system based on Knowledge Graph Retrieval-Augmented Generation (KG-RAG).

Repository: <https://github.com/anhkiet146/scientific-knowledge-graph-rag>

## Scope

The system builds a scientific knowledge graph from 482 scholarly articles published in the CTU Journal of Innovation and Sustainable Development between 2015 and 2025, then answers questions through graph search, context ranking, and LLM-based answer synthesis.

## Repository structure

```text
scientific-knowledge-graph-rag/
├── src/
│   ├── extraction/
│   ├── normalization/
│   ├── graph_construction/
│   ├── retrieval/
│   └── evaluation/
├── configs/
├── prompts/
├── schemas/
├── data/
│   ├── corpus_metadata.csv
│   ├── source_links.csv
│   ├── reference_json/
│   ├── extracted_json/
│   └── qa_evaluation/
├── results/
└── scripts/                    # runnable pipeline scripts
```

## Data policy

This repository should include only source code and derived research artifacts. It should not include:

- original PDF files;
- Gemini/OpenAI API keys;
- Neo4j or MongoDB passwords;
- `.env` files;
- personal or private data.

Original PDFs are represented by metadata only:

```csv
paper_id,title,year,doi,source_url
```

## Main pipeline

1. PDF parsing and text extraction.
2. LLM-based entity and relation extraction.
3. Entity/relation normalization.
4. Knowledge graph construction in Neo4j.
5. Query analysis and knowledge graph search.
6. Context ranking and filtering.
7. LLM answer synthesis.
8. Baseline comparison against lexical BM25 RAG and Vector RAG.

## Baseline comparison

The evaluation compares:

- Lexical BM25 RAG;
- Vector RAG;
- Proposed KG-RAG.

All methods use the same question set, answer model, top-k context setting, and evaluation criteria where possible.

The manuscript reports the following 45-question baseline comparison:

| Method | Faithfulness | Answer Relevancy | Context Precision | Context Recall | Latency (s) |
|---|---:|---:|---:|---:|---:|
| Lexical BM25 RAG | 0.800 | 0.811 | 0.789 | 0.620 | 27.963 |
| Vector RAG | 0.803 | 0.830 | 0.853 | 0.664 | 48.524 |
| Proposed KG-RAG | 0.837 | 0.866 | 0.868 | 0.865 | 24.516 |

The current summarized results are stored in:

- `results/baseline_comparison.csv`
- `results/qa_metrics.csv`
- `results/latency.csv`
- `data/qa_evaluation/comparison_results.jsonl`

## Configuration

Create a local `.env` file or local config file outside version control:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
MONGODB_URI=mongodb://localhost:27017
GEMINI_API_KEY=your_key
```

Never commit `.env` or API keys.

## Reproducing evaluation tables

The core pipeline scripts are located in `scripts/`. Evaluation and baseline-comparison utilities are located in `src/evaluation/`. After generating answers for all methods and applying judge scores, export:

- `results/baseline_comparison.csv`
- `results/qa_metrics.csv`
- `results/latency.csv`
