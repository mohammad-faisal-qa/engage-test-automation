"""Steps for the campaign lifecycle journey."""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from data.factories import (
    campaign_payload,
    cohort_contact,
    cohort_marker,
    condition,
    rule_segment_payload,
    unique_suffix,
)

pytestmark = [pytest.mark.e2e, pytest.mark.api]

scenarios("../features/campaign_lifecycle.feature")


@given(parsers.parse("a segment containing {count:d} customers"))
def a_segment_of_customers(journey, api, count):
    """Built through the API, never the interface.

    A cohort marker makes the segment resolve to exactly these customers, so a
    journey running beside three others still sends to its own audience.
    """
    marker = cohort_marker()
    contacts = api.contacts(role=journey.role, tenant=journey.tenant)
    journey.contacts = [
        contacts.create(cohort_contact(marker, plan="pro")) for _ in range(count)
    ]
    journey.segment = api.segments(role=journey.role, tenant=journey.tenant).create(
        rule_segment_payload(marker, condition("plan", "eq", "pro"))
    )


@given("a segment containing no customers")
def a_segment_with_nobody(journey, api):
    """A rule nobody satisfies — an empty audience is a state the product has to
    handle, not an error to engineer around."""
    journey.contacts = []
    journey.segment = api.segments(role=journey.role, tenant=journey.tenant).create(
        rule_segment_payload(
            cohort_marker(), condition("plan", "eq", f"nobody-{unique_suffix()}")
        )
    )


@given("a campaign targeting that segment")
def a_campaign_targeting_the_segment(journey, api):
    journey.campaign = api.campaigns(role=journey.role, tenant=journey.tenant).create(
        campaign_payload(segment_id=journey.segment.id, channel="email")
    )


@when("the campaign is sent")
def the_campaign_is_sent(journey, api, settings):
    """Records the outcome rather than asserting it.

    The same sentence appears in a journey that expects success and in one that
    expects refusal, and it should read identically in both — which it can only
    do if the step reports what happened instead of insisting.
    """
    delivery = api.delivery(role=journey.role, tenant=journey.tenant)
    journey.outcome = delivery.send_response(journey.campaign.id)

    if journey.outcome.status_code == 202:
        journey.deliveries = delivery.wait_until_sent(
            journey.campaign.id,
            timeout=settings.poll_timeout,
            interval=settings.poll_interval,
        )


@when("someone tries to mark the campaign as sent without sending it")
def someone_marks_it_sent(journey, api):
    journey.outcome = api.campaigns(
        role=journey.role, tenant=journey.tenant
    ).set_status_response(journey.campaign.id, "sent")


@when(parsers.parse("the provider reports that {delivered:d} were delivered and {opened:d} was opened"))
def the_provider_reports(journey, api, delivered, opened):
    delivery = api.delivery(role=journey.role, tenant=journey.tenant)
    for row in journey.deliveries[:delivered]:
        delivery.receipt(row.id, "delivered", idempotency_key=f"k-{unique_suffix()}")
    for row in journey.deliveries[:opened]:
        delivery.receipt(row.id, "opened", idempotency_key=f"k-{unique_suffix()}")


@then("every customer in the segment receives it")
def everyone_receives_it(journey):
    assert journey.outcome.status_code == 202
    assert {row.contact_id for row in journey.deliveries} == set(journey.contact_ids), (
        "the campaign did not reach exactly the customers in its segment"
    )


@then("the campaign is recorded as sent")
def the_campaign_is_recorded_as_sent(journey, api):
    campaign = api.campaigns(role=journey.role, tenant=journey.tenant).get_one(
        journey.campaign.id
    )
    assert campaign.status == "sent"


@then("the campaign is refused")
def the_campaign_is_refused(journey):
    assert journey.outcome.status_code == 422, (
        f"the shortcut was accepted with {journey.outcome.status_code}"
    )


@then("the campaign is still a draft")
def the_campaign_is_still_a_draft(journey, api):
    campaign = api.campaigns(role=journey.role, tenant=journey.tenant).get_one(
        journey.campaign.id
    )
    assert campaign.status == "draft"


@then("the send is refused because there is nobody to send to")
def refused_for_empty_audience(journey):
    assert journey.outcome.status_code == 422
    assert "audience" in journey.outcome.text.lower()


@then("nobody receives it")
def nobody_receives_it(journey, api):
    deliveries = api.delivery(
        role=journey.role, tenant=journey.tenant
    ).deliveries(journey.campaign.id)
    assert deliveries == []


@then(parsers.parse("the campaign reports {delivered:d} delivered and {opened:d} opened"))
def the_campaign_reports(journey, api, delivered, opened):
    stats = api.analytics(role=journey.role, tenant=journey.tenant).campaign(
        journey.campaign.id
    )
    assert stats.delivered == delivered
    assert stats.opened == opened


@then("the results never show more opens than deliveries")
def the_funnel_stays_monotonic(journey, api):
    stats = api.analytics(role=journey.role, tenant=journey.tenant).campaign(
        journey.campaign.id
    )
    assert stats.clicked <= stats.opened <= stats.delivered <= stats.sent <= stats.total
