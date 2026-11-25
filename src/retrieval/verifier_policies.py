from claim_verification import (
    verification_prompt, filter_claims, verification_prompt_v2, filter_claims_v2,
)
from claim_verification_experimental import (
    verification_prompt_experimental, filter_claims_experimental,
)
from claim_verification_literal import verification_prompt_literal, filter_claims_literal

POLICIES = {
    'v1': (verification_prompt, filter_claims),
    'v2': (verification_prompt_v2, filter_claims_v2),
    'content_numeric': (verification_prompt_experimental, filter_claims_experimental),
    'verbatim_value': (verification_prompt_literal, filter_claims_literal),
}


def verifier_policy(name):
    if name not in POLICIES:
        raise ValueError('Unknown verifier policy')
    return POLICIES[name]
