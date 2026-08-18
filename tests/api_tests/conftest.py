"""Fixtures shared by the API tests.

These are here rather than in the root conftest because they are about this
application's domain — cohorts, audiences, campaigns mid-send — and the root
file should stay about the session: settings, database state, clients.

The common thread is *privacy*. Segments are evaluated over every contact in the
tenant and campaigns send to whoever a segment resolves to, so a test that used
seeded data would be reading a set another xdist worker can change underneath
it. Everything below builds a set that belongs to one test alone.
"""

from __future__ import annotations

import pytest

from data.factories import (
    campaign_payload,
    cohort_contact,
    cohort_marker,
    condition,
    rule_segment_payload,
)


@pytest.fixture
def cohort(api):
    """A private set of contacts, plus the marker that isolates them.

    Yields `(marker, make)`. Every contact `make` creates carries the marker in
    `attributes.cohort`, so a segment with an `eq` condition on it resolves to
    exactly this test's contacts and nothing else in the database.
    """
    marker = cohort_marker()
    contacts = api.contacts()
    created = []

    def make(**overrides):
        contact = contacts.create(cohort_contact(marker, **overrides))
        created.append(contact)
        return contact

    yield marker, make

    # Best effort. The session reset is the real guarantee; this just stops a
    # long session accumulating rows nobody will look at again.
    for contact in created:
        contacts.delete_one_response(contact.id)


@pytest.fixture
def audience(api, cohort):
    """Two contacts and a segment that resolves to exactly those two.

    Two rather than one because several assertions are only meaningful with more
    than one delivery in play — "exactly one side effect" reads the same for a
    single row whether the code is idempotent or simply overwriting.
    """
    marker, make = cohort
    contacts = [make(plan="pro"), make(plan="pro")]
    segment = api.segments().create(
        rule_segment_payload(marker, condition("plan", "eq", "pro"))
    )
    return segment, contacts


@pytest.fixture
def campaign_with_audience(api, audience):
    """A draft campaign targeting a two-contact private segment.

    Targeting a segment, never the whole tenant: a campaign with no segment
    sends to every contact the tenant has, which on the seeded database is sixty
    deliveries per test and a much slower suite for no extra coverage.
    """
    segment, contacts = audience
    campaign = api.campaigns().create(
        campaign_payload(segment_id=segment.id, channel="email")
    )
    return campaign, contacts


@pytest.fixture
def sent_campaign(api, campaign_with_audience, settings):
    """A campaign whose send has completed, with its deliveries.

    The send is asynchronous — the endpoint returns 202 and the rows reach
    `sent` a moment later — so this polls to completion rather than sleeping a
    guessed number of seconds.
    """
    campaign, contacts = campaign_with_audience
    delivery = api.delivery()

    delivery.send(campaign.id)
    deliveries = delivery.wait_until_sent(
        campaign.id, timeout=settings.poll_timeout, interval=settings.poll_interval
    )

    assert len(deliveries) == len(contacts), (
        f"expected one delivery per audience contact ({len(contacts)}), "
        f"got {len(deliveries)}"
    )
    return campaign, deliveries
