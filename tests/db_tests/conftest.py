"""Fixtures for the database assertion layer.

Everything here skips cleanly when `TEST_DATABASE_URL` is unset, so a clone of
this repository runs green without a database. The database tests are an
addition to the suite, never a precondition for it.
"""

from __future__ import annotations

import pytest

from data.factories import (
    campaign_payload,
    cohort_contact,
    cohort_marker,
    condition,
    contact_payload,
    rule_segment_payload,
    unique_name,
    unique_suffix,
)
from utils.db import Database


@pytest.fixture(scope="session")
def db(settings) -> Database:
    """Read-only access, or a clean skip.

    Skipping rather than failing is the point: someone cloning this repository
    to read it should get a green run, and the absence of a database is a
    configuration choice rather than a broken environment.
    """
    if not settings.test_database_url:
        pytest.skip(
            "TEST_DATABASE_URL is not set, so the database assertions are "
            "skipped. Set it to a read-only-safe connection string for the "
            "same database the application under test is using."
        )
    return Database(settings.test_database_url)


@pytest.fixture(scope="module")
def stamped_rows(api, settings):
    """Put at least one row into each of the three tables HTTP cannot show.

    Built once for the module rather than per test: each send costs a real
    asynchronous wait, and the assertions that follow are about rows that exist,
    not about who created them.

    Everything is created through the API, exactly as every other test does it.
    The database layer reads; it never writes, not even to set itself up.
    """
    marker = cohort_marker()
    contacts = api.contacts()
    people = [contacts.create(cohort_contact(marker, plan="pro")) for _ in range(2)]

    segment = api.segments().create(
        rule_segment_payload(marker, condition("plan", "eq", "pro"))
    )
    campaign = api.campaigns().create(
        campaign_payload(segment_id=segment.id, channel="email")
    )

    delivery = api.delivery()
    delivery.send(campaign.id)
    deliveries = delivery.wait_until_sent(
        campaign.id, timeout=settings.poll_timeout, interval=settings.poll_interval
    )

    # A receipt, which is the only way a webhook_events row comes into being.
    key = f"db-layer-{unique_suffix()}"
    delivery.receipt(deliveries[0].id, "delivered", idempotency_key=key)

    # An impression, likewise for notification_impressions.
    notifications = api.notifications()
    notification = notifications.create(
        {"name": unique_name("Notification"),
         "frequency_cap": {"max_per_user": 5, "period_hours": 24}}
    )
    notifications.update_response(notification.id, {"status": "active"})
    impression = notifications.record_impression_response(notification.id, people[0].id)
    assert impression.status_code == 201, impression.text[:200]

    return {
        "tenant": "acme",
        "campaign_id": campaign.id,
        "delivery_ids": [d.id for d in deliveries],
        "idempotency_key": key,
        "notification_id": notification.id,
        "contact_ids": [p.id for p in people],
    }
