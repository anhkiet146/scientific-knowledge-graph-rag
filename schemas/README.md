# Strict v3 materialized payload

extracted_kg_strict_v3.schema.json validates extraction_result (not the outer candidate envelope). Metric-only Measurement is enforced with conditional JSON Schema; source grounding, relation endpoint signatures and review remain programmatic checks. The API transport replaces evidence quotes with evidence_ids and is snapshotted in each strict run manifest. Prior schema notes below are historical.

# Active versus historical schema

Use extracted_kg_review_v2_2.schema.json for the prepared rerun. Its seven entity types and five relation labels match reextract_review.py. Structural JSON Schema validation does not verify exact quotes, semantic support, endpoint signatures or human annotation independence; use the respective validators and independent review.

extracted_kg_schema.json is preserved as a historical four-relation artifact and must not validate the new five-relation run. Do not rename old labels as if their semantics were equivalent.

Paper MENTIONS Entity is graph provenance, not a predicted scientific relation. The graph builder now stores those links separately from the five scientific signatures and retains source evidence records. A new isolated graph is required; existing graphs are not migrated by this code change.
