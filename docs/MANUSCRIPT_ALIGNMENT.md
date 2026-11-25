# Manuscript alignment

The alignment profile is `configs/manuscript_alignment.json`. It records the
scope of the revised manuscript without rewriting historical observations.

## Historical evidence

- The authors identify the original web-based judge as OpenAI GPT-5.5. This is
  author-confirmed provenance, not a complete returned-model log or proof of a
  Responses API call at temperature zero.
- Scores are from an LLM rubric informed by RAGAS concepts. They are not a
  verified execution of the RAGAS software metrics.
- The 45 questions are internal development questions. The original QA report
  has one answer-generation run per system and different judge context formats.
  Score differences do not establish a causal graph benefit.
- The historical total of 9,575 entity records and the current 482-file count of
  9,608 refer to different snapshots. Neither proves the identity of the evaluated
  Neo4j graph. Manual normalization pair labels were not recovered.
- Hardware, embedding configuration and package versions measured today do not
  establish historical run settings. Missing measurements remain unknown.

## Current code

`scripts/normalize_entities.py --strategy source_preserving` preserves Unicode
NFC text, punctuation, comparison operators, units and case, while normalizing
whitespace. Author and Metric identities are scoped by paper. Source identifiers
and relation endpoints are retained; semantic aliases are not automatically
merged. The reviewed graph importer honors explicit paper identity scopes.
Within-paper disambiguation and normalization accuracy still require validation.

`--strategy exact` retains the historical NFKC/case-folding/punctuation-stripping
algorithm for auditing only. It can conflate `P > 0.05` and `P < 0.05`. Do not
present new source-preserving outputs as the data behind historical tables.
Every strategy requires a separate, empty output directory.

The active hybrid ranker uses nine signals. Its `semantic` field is a lexical
relevance score, not a dense embedding score. Default graph expansion is at most
two hops and default final context count is ten. No accepted evidence returns a
fixed refusal before synthesis. Experimental claim verification remains opt-in;
its presence in the code is not a measured hallucination-reduction result.

## New runs

Generate baseline answers first, then judge separately. This avoids silently
substituting a Gemini judge for the manuscript's author-confirmed GPT judge.
The API runner records the actual returned model, requested model, endpoint,
prompt hash and parameters. Failed calls never acquire a successful model label.
An API regrading is a new experiment, not a reconstruction of a web-based run.

```powershell
python src/evaluation/run_baseline_comparison.py --no-judge --vector-model sentence-transformers/all-MiniLM-L6-v2
python src/evaluation/judge_existing_results.py --input outputs/baseline_comparison/comparison_results.jsonl --output-dir outputs/gpt_regrading_new --provider openai --judge-model gpt-5.5 --reset
```

The baseline runner writes `run_metadata.json` with question/corpus hashes,
observed runtime versions and measured index-preparation durations. A vector
cache load is labeled as such, not as an index build. Index preparation and cached
translation are outside query latency. Native graph and passage request scopes
still differ, so their timings are not a fair end-to-end speed comparison.
Continuation metadata is appended; changed inputs/configuration are rejected.

No new extraction pass, database rebuild, paid evaluation or independent human
annotation is implied by this code release. The strict extraction v3 tools are
separate prospective workflows; their additional schema requirements do not
describe the historical seven-type extraction experiment.
