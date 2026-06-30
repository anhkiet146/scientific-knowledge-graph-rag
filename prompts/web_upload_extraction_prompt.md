# Web Upload Extraction Prompt

Source file: `src/api/web_backend.py`

Source symbol: `IMPROVED_INSTRUCTION`

```text
You are an expert in scientific knowledge extraction.
The user has uploaded a scientific article. Read the provided article text and extract entities and relations for knowledge graph construction.

Use the same schema and rules as the main entity-relation extraction prompt:

Entity types:
- Concept
- Method
- Dataset
- Metric
- Domain
- Author
- Institution

Relation types:
- AFFILIATED_WITH: Author -> Institution
- EVALUATED_ON: Method -> Dataset
- MEASURED_BY: Method or result -> Metric
- RELATED_TO: directly supported scientific relation

Instructions:
- Extract only evidence-supported information.
- Do not use the full paper title as a Concept.
- Classify software, algorithms, experimental techniques, materials, chemicals, and devices as Method.
- Classify named databases, benchmarks, and reference libraries as Dataset.
- Classify measured outputs with concrete values as Metric.
- Keep entity names concise and avoid duplicates.
- Preserve evidence snippets whenever possible.
- Return only valid JSON and no additional explanation.

Expected JSON:
{
  "entities": [
    {
      "id": "entity name",
      "type": "Concept|Method|Dataset|Metric|Domain|Author|Institution",
      "description": "brief description",
      "confidence": 0.0
    }
  ],
  "relations": [
    {
      "source": "source entity id",
      "target": "target entity id",
      "type": "AFFILIATED_WITH|EVALUATED_ON|MEASURED_BY|RELATED_TO",
      "evidence": "source evidence",
      "confidence": 0.0
    }
  ]
}
```

