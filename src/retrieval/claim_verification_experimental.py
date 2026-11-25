"""Opt-in structural guards; no runner uses this module by default."""
from collections import Counter
import re

from claim_verification import REFUSAL, filter_claims_v2, verification_prompt_v2

CONTENT_PATHS = (
    ('text',), ('author',), ('entity', 'id'), ('entity', 'description'),
    ('relation', 'source'), ('relation', 'target'),
    ('relation', 'description'), ('relation', 'evidence'),
)
NUMBER = re.compile(r'(?<![\w.])[-+−]?[0-9]+(?:[.,][0-9]+)*(?:[eE][-+]?[0-9]+)?(?!\w)')


def content_values(context):
    if not isinstance(context, dict):
        return []
    result = []
    for path in CONTENT_PATHS:
        value = context
        for key in path:
            if not isinstance(value, dict) or key not in value:
                break
            value = value[key]
        else:
            if isinstance(value, str):
                result.append((path, value))
    return result


def numeric_tokens(text):
    return Counter(token.replace('−', '-') for token in NUMBER.findall(text))


def verification_prompt_experimental(question, answer, contexts):
    return verification_prompt_v2(question, answer, contexts) + (
        '\nAdditional constraints: quote only content values at these paths: '
        + ', '.join('.'.join(path) for path in CONTENT_PATHS)
        + '. Never use filenames, paper_id, source_file, titles, or labels as scientific evidence. '
        'Copy numeric forms and signs from evidence; do not convert units or number formats. '
        'Matching a number does not establish the same object, condition, unit, or meaning.'
    )


def filter_claims_experimental(answer, contexts, verdict):
    _, audit = filter_claims_v2(answer, contexts, verdict)
    accepted = []
    for record in audit:
        record['guard_version'] = 'experimental-content-numeric-v1'
        if not record['accepted']:
            continue
        quote = record['quote']
        matches = [list(path) for path, value in content_values(contexts[record['context_index']]) if quote in value]
        record['content_paths'] = matches
        if not matches:
            record['reasons'].append('quote_not_in_allowed_content')
        claim_numbers = numeric_tokens(record['matched_draft_span'])
        quote_numbers = numeric_tokens(quote)
        if claim_numbers - quote_numbers:
            record['reasons'].append('numeric_token_or_sign_not_in_quote')
        record['accepted'] = not record['reasons']
        record['numeric_check_scope'] = 'Standalone Arabic numeric tokens only; exact form except Unicode minus'
        if record['accepted']:
            accepted.append(record['matched_draft_span'])
    return ('\n'.join('- ' + text for text in accepted) if accepted else REFUSAL), audit
