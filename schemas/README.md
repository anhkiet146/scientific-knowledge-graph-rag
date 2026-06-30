# Schemas

The `schemas/` directory documents the JSON structures used by the pipeline.

It does not contain experimental results. It contains format definitions so that other users can understand or validate files in:

- `data/extracted_json/`
- `data/graph_json/`

Current schema:

- `extracted_kg_schema.json`: JSON Schema for the entity/relation extraction output used before Neo4j graph loading.

The schema is intentionally permissive with `additionalProperties: true` because the implementation may preserve extra provenance fields such as section name, paper id, source evidence, or confidence values.

