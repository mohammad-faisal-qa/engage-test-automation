"""Steps for the onsite notification frequency-cap journey."""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from data.factories import contact_payload, unique_name

pytestmark = [pytest.mark.e2e, pytest.mark.api]

scenarios("../features/onsite_frequency_cap.feature")


def create_notification(api, journey, *, cap: int, status: str):
    notifications = api.notifications(role=journey.role, tenant=journey.tenant)
    notification = notifications.create(
        {
            "name": unique_name("Notification"),
            "frequency_cap": {"max_per_user": cap, "period_hours": 24},
        }
    )
    # Created as a draft, so it has to be moved into the state the journey
    # describes. "Running" is a business state, not a UI toggle.
    response = notifications.update_response(notification.id, {"status": status})
    assert response.status_code == 200, response.text[:200]
    journey.notification = notification
    return notification


@given(parsers.parse("an active notification capped at {cap:d} showings per day"))
def an_active_notification(journey, api, cap):
    create_notification(api, journey, cap=cap, status="active")


@given(parsers.parse("a paused notification capped at {cap:d} showings per day"))
def a_paused_notification(journey, api, cap):
    create_notification(api, journey, cap=cap, status="paused")


@given("a customer who has never seen it")
def a_customer_who_has_never_seen_it(journey, api):
    journey.contacts = [
        api.contacts(role=journey.role, tenant=journey.tenant).create(contact_payload())
    ]


@given(parsers.parse("a customer who has already seen it {times:d} times"))
def a_customer_who_has_seen_it(journey, api, times):
    contacts = api.contacts(role=journey.role, tenant=journey.tenant)
    contact = contacts.create(contact_payload())
    journey.contacts = [contact]

    notifications = api.notifications(role=journey.role, tenant=journey.tenant)
    for _ in range(times):
        response = notifications.record_impression_response(
            journey.notification.id, contact.id
        )
        assert response.status_code == 201, response.text[:200]


@when("we ask whether the customer should be shown the notification")
def we_ask_about_eligibility(journey, api):
    journey.outcome = api.notifications(
        role=journey.role, tenant=journey.tenant
    ).eligibility(journey.notification.id, journey.contacts[0].id)


@then("the answer is yes")
def the_answer_is_yes(journey):
    assert journey.outcome["eligible"] is True, (
        f"expected the customer to be eligible, got {journey.outcome}"
    )
    assert journey.outcome["reason"] == "eligible"


@then("the answer is no because they have seen it enough")
def capped(journey):
    assert journey.outcome["eligible"] is False
    assert journey.outcome["reason"] == "frequency_capped", (
        f"refused for the wrong reason: {journey.outcome}"
    )
    assert journey.outcome["impressions_in_window"] >= journey.outcome["cap"]


@then("the answer is no because the notification is not running")
def not_running(journey):
    assert journey.outcome["eligible"] is False
    assert journey.outcome["reason"] == "notification_not_active", (
        f"refused for the wrong reason: {journey.outcome}"
    )
