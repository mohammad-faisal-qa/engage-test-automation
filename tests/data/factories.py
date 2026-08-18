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


# --- segments ---------------------------------------------------------------
#
# Rule segments are evaluated over every contact in the tenant, which makes them
# the one place where another worker's data can leak into an assertion. The
# answer is a cohort marker: each test stamps a unique value into
# `attributes.cohort` on the contacts it creates, and every segment it builds
# carries an `eq` condition on that marker alongside the field actually under
# test. Membership is then exactly this test's contacts, whatever else is in the
# database, and `-n 4` changes nothing.

COHORT_FIELD = "cohort"


def cohort_marker() -> str:
    """A value no other test will use."""
    return f"cohort-{unique_suffix()}"


def cohort_contact(cohort: str, **overrides: Any) -> dict[str, Any]:
    """A contact tagged into one cohort. Attribute overrides merge, not replace."""
    payload = contact_payload()
    attributes = payload["attributes"] | {COHORT_FIELD: cohort}
    attributes.update(overrides.pop("attributes", {}))
    payload.update(overrides)
    payload["attributes"] = attributes
    return payload


def condition(field: str, op: str, value: Any) -> dict[str, Any]:
    return {"field": field, "op": op, "value": value}


def rule_segment_payload(
    cohort: str,
    *conditions: dict[str, Any],
    match: str = "all",
) -> dict[str, Any]:
    """A rule segment scoped to one cohort.

    The cohort condition is prepended rather than left to the caller, so it
    cannot be forgotten — a segment without it would match other workers' rows.

    Note it is only sound with `match="all"`. Under `any` the cohort condition
    would widen the segment instead of narrowing it, so tests needing `any` use
    `rule_segment_payload_any`, which nests the real conditions under the
    cohort by intersecting the result in the test instead.
    """
    return {
        "name": unique_name("Segment"),
        "kind": "rule",
        "rules": {
            "match": match,
            "conditions": [condition(COHORT_FIELD, "eq", cohort), *conditions],
        },
    }


def unscoped_rule_segment_payload(
    *conditions: dict[str, Any], match: str = "all"
) -> dict[str, Any]:
    """A rule segment with no cohort condition.

    For `match="any"` tests, where a cohort condition would broaden rather than
    narrow. Those tests must intersect the returned members against the ids they
    created rather than asserting on the whole membership.
    """
    return {
        "name": unique_name("Segment"),
        "kind": "rule",
        "rules": {"match": match, "conditions": list(conditions)},
    }


def static_segment_payload(contact_ids: list[int]) -> dict[str, Any]:
    return {
        "name": unique_name("Static"),
        "kind": "static",
        "rules": {"contact_ids": contact_ids},
    }
