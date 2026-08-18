"""The segment rule evaluator.

This is the most interesting module in the application, for one reason: a rule
names a *field*, and that field may be either a real column on the contacts
table or a key inside the `attributes` JSON. `plan` is a column. `lifetime_value`
is not — it lives in JSONB. The evaluator has to serve both from one rule
syntax, and a change that broke either half would leave the other passing.

Every test here builds its own cohort. Rule segments are evaluated over every
contact in the tenant, so without that, a segment matching `plan = enterprise`
would also match the forty seeded contacts and anything another xdist worker
happened to create mid-assertion. Each test stamps a unique marker into
`attributes.cohort` and every segment carries an `eq` condition on it, which
makes membership exactly the set the test built.
"""

import allure
import pytest

from data.factories import (
    COHORT_FIELD,
    condition,
    rule_segment_payload,
    unique_suffix,
    unscoped_rule_segment_payload,
)

pytestmark = [pytest.mark.api]


def member_ids(api, segment_id) -> set[int]:
    return {contact.id for contact in api.segments().members(segment_id)}


@allure.feature("Segments")
@allure.story("A rule on a real column selects by that column")
def test_a_rule_on_a_column_field_selects_by_that_column(api, cohort):
    """`plan` is a column on the contacts table."""
    marker, make = cohort
    enterprise = make(plan="enterprise")
    pro = make(plan="pro")

    segment = api.segments().create(
        rule_segment_payload(marker, condition("plan", "eq", "enterprise"))
    )

    members = member_ids(api, segment.id)
    assert enterprise.id in members
    assert pro.id not in members, "a plan=pro contact matched plan eq enterprise"


@allure.feature("Segments")
@allure.story("A rule on a JSONB attribute selects by that attribute")
def test_a_rule_on_a_jsonb_attribute_selects_by_that_attribute(api, cohort):
    """`lifetime_value` is not a column — it is a key inside `attributes`.

    This is the half of the evaluator that a column-only implementation would
    fail, and it would fail silently: an unknown field reads as `None`, `None`
    matches nothing, and the segment would simply come back empty rather than
    erroring. So the assertion has to be that the *right* contact is in, not
    merely that the call succeeded.
    """
    marker, make = cohort
    high = make(attributes={"lifetime_value": 9000})
    low = make(attributes={"lifetime_value": 100})

    segment = api.segments().create(
        rule_segment_payload(marker, condition("lifetime_value", "gt", 5000))
    )

    members = member_ids(api, segment.id)
    assert high.id in members, (
        "a contact with lifetime_value 9000 did not match `gt 5000` — the "
        "evaluator is not reading JSONB attributes"
    )
    assert low.id not in members


@allure.feature("Segments")
@allure.story("One rule set can mix a column and a JSONB attribute")
def test_one_rule_set_can_mix_a_column_and_a_jsonb_attribute(api, cohort):
    """The case that proves the two lookups compose rather than merely coexist."""
    marker, make = cohort
    both = make(plan="enterprise", attributes={"lifetime_value": 9000})
    column_only = make(plan="enterprise", attributes={"lifetime_value": 10})
    attribute_only = make(plan="free", attributes={"lifetime_value": 9000})

    segment = api.segments().create(
        rule_segment_payload(
            marker,
            condition("plan", "eq", "enterprise"),
            condition("lifetime_value", "gt", 5000),
        )
    )

    members = member_ids(api, segment.id)
    assert both.id in members
    assert column_only.id not in members, "matched on the column alone"
    assert attribute_only.id not in members, "matched on the attribute alone"


@allure.feature("Segments")
@allure.story("match=any is a union, match=all is an intersection")
def test_match_any_is_a_union_not_an_intersection(api, cohort):
    """`any` cannot use the cohort trick — a cohort condition under `any` would
    widen the segment rather than narrow it. So this one asserts against the
    ids it created instead of against the whole membership.
    """
    marker, make = cohort
    unique_plan = f"plan-{unique_suffix()}"

    in_cohort = make(plan="pro")
    by_plan = make(plan=unique_plan, attributes={COHORT_FIELD: f"other-{unique_suffix()}"})

    segment = api.segments().create(
        unscoped_rule_segment_payload(
            condition(COHORT_FIELD, "eq", marker),
            condition("plan", "eq", unique_plan),
            match="any",
        )
    )

    members = member_ids(api, segment.id)
    assert in_cohort.id in members, "the cohort condition alone did not admit its contact"
    assert by_plan.id in members, "the plan condition alone did not admit its contact"

    intersection = api.segments().create(
        unscoped_rule_segment_payload(
            condition(COHORT_FIELD, "eq", marker),
            condition("plan", "eq", unique_plan),
            match="all",
        )
    )
    assert member_ids(api, intersection.id) & {in_cohort.id, by_plan.id} == set(), (
        "the same two conditions under match=all admitted a contact that "
        "satisfies only one of them"
    )


@allure.feature("Segments")
@allure.story("The in operator matches any listed value")
def test_the_in_operator_matches_any_of_the_listed_values(api, cohort):
    marker, make = cohort
    us = make(country="US")
    gb = make(country="GB")
    de = make(country="DE")

    segment = api.segments().create(
        rule_segment_payload(marker, condition("country", "in", ["US", "GB"]))
    )

    members = member_ids(api, segment.id)
    assert {us.id, gb.id} <= members
    assert de.id not in members


@allure.feature("Segments")
@allure.story("The contains operator ignores case")
def test_the_contains_operator_ignores_case(api, cohort):
    """Worth its own test because Postgres `LIKE` is case-sensitive: an
    implementation that reached for SQL rather than evaluating in Python would
    pass for exact case and fail here.
    """
    marker, make = cohort
    target = make(first_name="Genevieve")
    other = make(first_name="Robert")

    segment = api.segments().create(
        rule_segment_payload(marker, condition("first_name", "contains", "GENEV"))
    )

    members = member_ids(api, segment.id)
    assert target.id in members, "contains did not match across a case difference"
    assert other.id not in members


@allure.feature("Segments")
@allure.story("gt and lt compare numbers numerically")
def test_gt_compares_numerically_rather_than_as_text(api, cohort):
    """The bug this catches is a real one and reads as correct until you try it:
    compared as strings, "9" > "100", because "9" sorts after "1". A contact
    worth 9 would then match `gt 50` and one worth 100 would not.
    """
    marker, make = cohort
    hundred = make(attributes={"lifetime_value": 100})
    nine = make(attributes={"lifetime_value": 9})

    segment = api.segments().create(
        rule_segment_payload(marker, condition("lifetime_value", "gt", 50))
    )

    members = member_ids(api, segment.id)
    assert hundred.id in members, "100 did not match `gt 50`"
    assert nine.id not in members, (
        "9 matched `gt 50`, so the comparison is lexicographic rather than numeric"
    )


@allure.feature("Segments")
@allure.story("A rule set with no conditions matches nobody")
def test_a_rule_set_with_no_conditions_matches_nobody(api, cohort):
    """Empty means empty, not everything.

    The opposite choice is defensible in the abstract and catastrophic in
    practice: a half-built segment saved with no conditions would resolve to
    every contact in the tenant, and the next campaign pointed at it would send
    to all of them.
    """
    marker, make = cohort
    make(plan="pro")

    segment = api.segments().create(unscoped_rule_segment_payload(match="all"))

    assert api.segments().members(segment.id) == [], (
        "a segment with no conditions returned members — an unfinished segment "
        "would target the entire tenant"
    )
