# Scientific Knowledge Graph RAG

Source-traceable scientific extraction, graph retrieval and question answering
for the PAPER023031-1 project.

## Revised manuscript scope

Read [the alignment guide](docs/MANUSCRIPT_ALIGNMENT.md) before reproducing any
table. Historical QA scores, graph counts and normalization pair statistics are
not newly validated by this code release. The original 40-paper reference
provenance and manual normalization labels remain unresolved. The repository's
existing `results/` files are historical artifacts, not rerun measurements.

The original judge is identified by the authors as **OpenAI GPT-5.5**. Its web-based
scores use an LLM rubric informed by RAGAS concepts. API configuration is not
inferred from that model name. New API judging records actual response metadata.

## Setup

Use Python 3.11 or newer in a virtual environment:

```powershell
python -m pip install -r requirements.txt
Copy-Item configs/config.example.env .env
```

Fill credentials locally through environment variables or `.env`. Keep keys and
passwords out of Git. Set `CORPUS_JSON_DIR` to parsed article JSON and
`QA_TEST_SET_FILE` to the intended internal question file. The default question
file is `data/qa_evaluation/qa_test_set.py`; reference correctness is not asserted.

## Existing extraction files

No re-extraction is required to normalize the existing records:

```powershell
python scripts/normalize_entities.py --input data/extracted_json --output outputs/normalized_new --strategy source_preserving
```

The source-preserving mode keeps numerical operators, units, punctuation and
case. Author and Metric identities are scoped by paper. `--strategy exact`
replays the legacy punctuation-stripping rule only for historical audits. New
outputs never replace the original extraction files or historical measurements.

Graph import requires reviewed inputs and a separately selected test database.
It does not clear existing data. Configure `NEO4J_DATABASE` and MongoDB isolation
before running `scripts/build_graph.py` and `scripts/serve_api.py`.

## Evaluation

```powershell
python src/evaluation/run_baseline_comparison.py --no-judge
python src/evaluation/judge_existing_results.py --input outputs/baseline_comparison/comparison_results.jsonl --output-dir outputs/gpt_regrading_new --provider openai --judge-model gpt-5.5 --reset
```

These commands use paid model APIs. They do not reproduce the historical web
judgments automatically. Save each study to its own output directory. The
baseline runner records corpus/question hashes, installed package versions,
index preparation and cache status separately from request latency. Native
baseline timing boundaries differ; do not interpret their difference as a
retrieval-method speed advantage.

Default retrieval uses at most two hops, nine ranking signals and ten final
contexts. The `semantic` ranking signal is lexical relevance. Claim verification
is experimental and disabled by default; no hallucination-reduction score is
claimed. The strict extraction tools in `docs/STRICT_V3_GUIDE_VI.md` are a separate
prospective workflow, not the historical extraction protocol.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The unit tests use synthetic records and mocked services. A green test suite is
not independent scientific validation or a completed live Neo4j benchmark.

## Data and publication

Original PDFs, credentials, local run directories and unpublished annotation
records are excluded from this code update. Public availability and consistency
of historical gold/reference artifacts must be checked separately. See
`configs/manuscript_alignment.json` for explicit historical and current scopes.
