# Evidence-ID transport prototype — offline, not yet evaluated with an API

Use the current operational seven entity types and five directed signatures.
The source is an evidence catalog bound to one article snapshot. Return
entities with id/type/description/evidence_ids and relations with
source/type/target/evidence_ids. evidence_ids must contain existing catalog IDs.
Do not return copied quotes or fabricate IDs. Software will resolve each ID
to exact source bytes. Synthetic examples are never current-article evidence.

An existing ID proves only that a source fragment exists. Select fragments that
actually support the complete scientific assertion, its role and attribution.
For a numerical table result cite both the relevant row and the headers that
establish the metric, sample/model, unit and condition. Do not infer mappings
from unreadable or ambiguous layout. Omit unsupported results.

A Metric requires a measured numerical value, not merely a version number,
epoch setting, sample size, “high”, “fast” or “acceptable”. A biological object
does not become a Dataset to create a relation. Do not change an investigated
object into a Method solely to connect a result. Preserve conflicting source
reports separately with explicit qualifiers; never silently reconcile units.

This prototype does not replace the active prompts or establish independent
gold. It requires a separate structured transport schema, API pilot and manual
semantic evaluation before production use. No accuracy or cost gain is claimed.
