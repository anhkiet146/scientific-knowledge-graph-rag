"""Opt-in evidence-value copying, with a deliberate loss of paraphrase coverage."""
import unicodedata

from claim_verification import REFUSAL
from claim_verification_experimental import content_values, filter_claims_experimental

POLICY = 'verbatim_value_v1'


def literal_surface(text):
    return ' '.join(unicodedata.normalize('NFC', text).split())


def verification_prompt_literal(question, answer, contexts):
    from claim_verification_experimental import verification_prompt_experimental
    return verification_prompt_experimental(question, answer, contexts) + (
        '\nVerbatim-value mode: retain a claim only when its unchanged draft span '
        'copies one entire allowed evidence string value. Do not paraphrase, '
        'translate, remove a negation, convert a unit, or select a fragment from '
        'a longer value. Copy the full value as quote. Values containing a '
        'semicolon are ineligible because this mode does not split compound '
        'records. If none qualifies, return {"claims":[]}. This is extractive '
        'filtering, not an independent truth or atomicity judgment.'
    )


def filter_claims_literal(answer, contexts, verdict):
    _, audit = filter_claims_experimental(answer, contexts, verdict)
    accepted = []
    for record in audit:
        record['guard_version'] = POLICY
        record['semantic_entailment_proven'] = False
        record['source_pdf_verified'] = False
        if not record['accepted']:
            continue
        span = literal_surface(record['text'])
        target = span
        quote = record['quote']
        values = content_values(contexts[record['context_index']])
        paths = [list(path) for path, value in values
                 if value == quote and literal_surface(value) == target]
        record['whole_value_paths'] = paths
        if target not in literal_surface(answer):
            record['reasons'].append('verbatim_claim_not_in_draft')
        if not paths:
            record['reasons'].append('claim_not_entire_evidence_value')
        if any(mark in span or mark in quote for mark in (';', '；')):
            record['reasons'].append('compound_value_requires_separate_evidence')
        record['accepted'] = not record['reasons']
        if record['accepted']:
            accepted.append(span)
    return ('\n'.join('- ' + text for text in accepted) if accepted else REFUSAL), audit
