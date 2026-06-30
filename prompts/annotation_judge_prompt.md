# Annotation Judge Prompt

Source file: `src/evaluation/evaluate_with_judge.py`

Source symbol: `ANNOTATOR_PROMPT`

```text
You are an expert annotator for scientific information extraction.
Read the article text and create reference annotations for entities and relations.

Allowed entity types:
- Concept: central scientific concept, object, problem, or phenomenon.
- Method: method, model, algorithm, technique, material, chemical, device, or software.
- Dataset: named dataset, benchmark, database, or data source.
- Metric: measured result or quantitative indicator with a concrete value.
- Domain: main scientific field.
- Author: individual author.
- Institution: organization associated with an author or the study.

Allowed relation types:
- AFFILIATED_WITH: Author -> Institution
- EVALUATED_ON: Method -> Dataset
- MEASURED_BY: Method/result -> Metric
- RELATED_TO: direct scientific association supported by the text

Article text:
{paper_text}

Return only valid JSON:
{
  "entities": [
    {"id": "short entity name", "type": "entity type"}
  ],
  "relations": [
    {"source": "source entity id", "target": "target entity id", "type": "relation type"}
  ]
}
```

