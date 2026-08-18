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

import httpx
import pytest

from data.constants import CAMPAIGN_SENT, SEGMENT_ENTERPRISE_RULE
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


@pytest.fixture(scope="session")
def openapi(settings) -> dict:
    """The application's own published contract, fetched once.

    Session-scoped because it cannot change while the process under test is
    running, and fetching it per test would add a request to every contract
    assertion for no new information.
    """
    url = f"{settings.api_base_url}/openapi.json"
    response = httpx.get(url, timeout=settings.request_timeout)
    if response.status_code != 200:
        raise RuntimeError(
            f"Could not fetch the OpenAPI document from {url} "
            f"({response.status_code}). Contract tests have nothing to validate "
            f"against without it."
        )
    document = response.json()
    if "components" not in document or "schemas" not in document["components"]:
        raise RuntimeError(
            f"{url} returned a document with no component schemas, so there is "
            f"no declared contract to check responses against."
        )
    return document


@pytest.fixture(scope="session")
def live_responses(api) -> dict[str, dict]:
    """One real response body per critical model, taken from seeded data.

    Raw dictionaries, deliberately — not parsed models. Parsing through the
    suite's own Pydantic classes would discard exactly what these tests exist to
    inspect: unexpected keys, and values whose type the model was willing to
    coerce.
    """
    raw = api.raw()
    campaign_id = CAMPAIGN_SENT

    page = raw.get("/api/contacts", params={"size": 1}, expect=200).json()
    deliveries = raw.get(f"/api/campaigns/{campaign_id}/deliveries", expect=200).json()

    assert page["items"], "no seeded contacts to validate a response against"
    assert deliveries, f"seeded campaign {campaign_id} has no deliveries to validate"

    return {
        "ContactOut": page["items"][0],
        "SegmentOut": raw.get(f"/api/segments/{SEGMENT_ENTERPRISE_RULE}", expect=200).json(),
        "CampaignOut": raw.get(f"/api/campaigns/{campaign_id}", expect=200).json(),
        "DeliveryOut": deliveries[0],
        "CampaignStats": raw.get(
            f"/api/analytics/campaigns/{campaign_id}", expect=200
        ).json(),
    }
