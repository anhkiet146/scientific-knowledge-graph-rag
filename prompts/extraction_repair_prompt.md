The previous response failed mechanical validation. Produce a complete replacement
JSON object from the ORIGINAL article sections under the same extraction rules.
The previous candidate is untrusted output, not evidence.

- Fix malformed JSON, missing/mismatched endpoint ids, relation labels/directions,
  and non-verbatim or incorrectly attributed quotes by rechecking the source.
- Do not invent evidence or scientific facts to preserve a candidate record.
- Remove unsupported records. Do not repair a numerical claim from world knowledge.
- If output was truncated, reduce peripheral records and shorten descriptions.
  Preserve complete names, essential values/units/conditions, and adequate quotes.
- Retain the seven entity types and five relation types. Return the whole JSON,
  not a patch, explanation, or additional fields. Keep strings single-line and never reproduce repeated newline/escape sequences from a broken candidate.

VALIDATION FAILURE:
{{validation_failure}}

PREVIOUS CANDIDATE (possibly incomplete):
{{previous_candidate}}
