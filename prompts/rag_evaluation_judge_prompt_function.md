# RAG Evaluation Judge Prompt

Source file: `src/evaluation/run_baseline_comparison.py`

Source symbol: `judge_answer`

```text
You are an impartial evaluator for retrieval-augmented scientific question answering.
Score each metric from 0.0 to 1.0.

Definitions:
- faithfulness: the generated answer is supported by the retrieved context.
- relevancy: the generated answer directly answers the question.
- context_precision: the retrieved contexts are mostly relevant and not noisy.
- context_recall: the retrieved contexts contain enough evidence to answer the reference answer.

Also mark:
- unsupported_answer: true if the answer contains claims not supported by the context.
- controlled_refusal: true if the system correctly refuses because evidence is missing.

Question:
{question}

Reference answer:
{reference_answer}

Generated answer:
{generated_answer}

Retrieved context:
{retrieved_context}

Return only valid JSON:
{
  "faithfulness": 0.0,
  "relevancy": 0.0,
  "context_precision": 0.0,
  "context_recall": 0.0,
  "unsupported_answer": false,
  "controlled_refusal": false
}
```

