# Query Translation Prompt

Source file: `src/evaluation/run_baseline_comparison.py`

Source symbol: `translate_questions`

```text
Translate the following Vietnamese scientific question into natural English for information retrieval.

Rules:
- Keep proper nouns unchanged.
- Keep formulas, species names, chemical names, model names, metric names, dataset names, and paper titles unchanged.
- Preserve the specific information need.
- Return only the English translation. Do not explain.

Question:
{question}
```

