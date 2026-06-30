# KG-RAG Intent Detection Prompt

Source file: `src/retrieval/graphrag_engine.py`

Source symbol: `INTENT_DETECTION_PROMPT`

```text
Classify the following user question into exactly one of two intents:

- "graph": the question is about scientific content, research papers, authors, methods, datasets, metrics, AI/ML models, experiments, or any academic topic that should be answered from the knowledge graph.
- "general": the question is a greeting, casual conversation, arithmetic, system capability question, or general request that does not require retrieval from the scientific knowledge graph.

Rule: If the question contains any academic term, paper title, author name, dataset name, model name, method name, metric, chemical/species name, or research object, choose "graph".

Question: "{question}"

Return only valid JSON:
{"intent": "graph"}
or
{"intent": "general"}
```

