"""Steps for the segment targeting journey."""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from data.factories import (
    cohort_contact,
    cohort_marker,
    condition,
    rule_segment_payload,
    unscoped_rule_segment_payload,
)

pytestmark = [pytest.mark.e2e, pytest.mark.api]

scenarios("../features/segment_targeting.feature")

# Whether a field is a column on the customer record or one of their recorded
# attributes is exactly the distinction a marketer should not have to make, so
# the feature file does not — the mapping lives here instead.
COLUMN_FIELDS = {"plan", "country", "first_name", "last_name", "email"}


def customer_with(marker: str, field: str, value: str) -> dict:
    if field in COLUMN_FIELDS:
        return cohort_contact(marker, **{field: value})
    coerced = int(value) if value.isdigit() else value
    return cohort_contact(marker, attributes={field: coerced})


@given(parsers.parse('a customer whose {field} is "{value}"'))
def a_customer_whose_field_is(journey, api, field, value):
    if not getattr(journey, "marker", None):
        journey.marker = cohort_marker()
    contacts = api.contacts(role=journey.role, tenant=journey.tenant)
    journey.contacts.append(contacts.create(customer_with(journey.marker, field, value)))


@when(parsers.parse('a segment selects customers whose {field} is "{value}"'))
def a_segment_selects(journey, api, field, value):
    coerced = int(value) if value.isdigit() else value
    journey.segment = api.segments(role=journey.role, tenant=journey.tenant).create(
        rule_segment_payload(journey.marker, condition(field, "eq", coerced))
    )


@when("a segment is created with no rules at all")
def a_segment_with_no_rules(journey, api):
    journey.segment = api.segments(role=journey.role, tenant=journey.tenant).create(
        unscoped_rule_segment_payload(match="all")
    )


@then("only the first customer is in the segment")
def only_the_first_customer(journey, api):
    members = api.segments(role=journey.role, tenant=journey.tenant).members(
        journey.segment.id
    )
    ids = {contact.id for contact in members}
    first, second = journey.contacts[0], journey.contacts[1]
    assert first.id in ids, "the matching customer was not selected"
    assert second.id not in ids, "a customer who does not match was selected"


@then("the segment contains nobody")
def the_segment_contains_nobody(journey, api):
    members = api.segments(role=journey.role, tenant=journey.tenant).members(
        journey.segment.id
    )
    assert members == [], (
        "a segment with no rules selected customers — an unfinished segment "
        "would target the whole organisation"
    )
