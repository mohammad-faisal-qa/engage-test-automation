"""Builders for test data that cannot collide.

Every name and email carries a UUID fragment. That single decision is what
makes `-n 4` safe: two workers running the same test at the same moment create
`contact.a1b2c3d4@…` and `contact.9f8e7d6c@…`, never the same row twice, and
neither can see a unique-constraint violation caused by the other.

The builders return plain dicts rather than models on purpose — a test for a
*rejected* payload needs to send something invalid, which a validating model
would refuse to construct.
"""

from __future__ import annotations

import uuid
from typing import Any

# Reserved for documentation by IANA, so no address here can ever reach a real
# mailbox — and, unlike `.test`, it survives the API's email validation.
TEST_EMAIL_DOMAIN = "qa.example.com"


def unique_suffix() -> str:
    """Eight hex characters: short enough to read in a report, wide enough
    (4 billion values) that a collision within one run is not a real risk."""
    return uuid.uuid4().hex[:8]


def unique_email(prefix: str = "contact") -> str:
    return f"{prefix}.{unique_suffix()}@{TEST_EMAIL_DOMAIN}"


def unique_name(prefix: str) -> str:
    return f"{prefix} {unique_suffix()}"


def contact_payload(**overrides: Any) -> dict[str, Any]:
    """A valid contact. Override any field to make it invalid on purpose."""
    suffix = unique_suffix()
    payload: dict[str, Any] = {
        "email": f"contact.{suffix}@{TEST_EMAIL_DOMAIN}",
        "first_name": "Test",
        "last_name": f"Contact{suffix}",
        "country": "US",
        "plan": "pro",
        "attributes": {
            "lifetime_value": 2500,
            "signup_source": "automation",
            "newsletter": True,
        },
    }
    payload.update(overrides)
    return payload


def segment_payload(**overrides: Any) -> dict[str, Any]:
    """A rule segment matching on `plan`, which is a real column."""
    payload: dict[str, Any] = {
        "name": unique_name("Segment"),
        "kind": "rule",
        "rules": {
            "match": "all",
            "conditions": [{"field": "plan", "op": "eq", "value": "enterprise"}],
        },
    }
    payload.update(overrides)
    return payload


def campaign_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": unique_name("Campaign"),
        "channel": "email",
        "segment_id": None,
    }
    payload.update(overrides)
    return payload
