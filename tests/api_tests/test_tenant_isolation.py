"""Multi-tenancy: one tenant's data must be invisible to another."""

import allure
import pytest

from data.constants import (
    ACME_CONTACT_ID,
    CAMPAIGN_DRAFT,
    CAMPAIGN_GLOBEX_DRAFT,
    GLOBEX_CONTACT_ID,
    SEGMENT_ENTERPRISE_RULE,
    SEGMENT_GLOBEX_FREE,
)
from data.factories import campaign_payload, contact_payload, static_segment_payload

pytestmark = [pytest.mark.api]


@pytest.mark.readonly
@pytest.mark.smoke
@allure.feature("Tenant isolation")
@allure.story("Another tenant's contact is not found, rather than forbidden")
def test_a_contact_from_another_tenant_reads_as_not_found(api):
    """404, specifically not 403 — and that distinction is the whole test.

    Both statuses deny the request, so both look secure. But 403 means "this
    exists and you may not have it", which confirms the id is real. Anyone can
    then walk the id space and learn exactly how many customers the other
    tenant has, and which ids to target elsewhere. 404 says only "no such
    contact for you", which leaks nothing.

    The control assertion matters as much: the same call against the caller's
    *own* contact must succeed. Without it, a broken endpoint returning 404 for
    everything would pass this test while being entirely non-functional.
    """
    acme_admin = api.contacts(role="admin", tenant="acme")

    with allure.step(f"Read acme's own contact {ACME_CONTACT_ID}"):
        own = acme_admin.get_one_response(ACME_CONTACT_ID)
    assert own.status_code == 200, "the control read failed; the test below would prove nothing"
    assert own.json()["tenant_id"] == "acme"

    with allure.step(f"Read globex's contact {GLOBEX_CONTACT_ID} with an acme token"):
        other = acme_admin.get_one_response(GLOBEX_CONTACT_ID)

    assert other.status_code == 404, (
        f"expected 404 for another tenant's contact, got {other.status_code}. "
        f"403 would confirm the row exists and leak globex's id space."
    )

    with allure.step("Confirm the contact does exist, for its own tenant"):
        owner = api.contacts(role="admin", tenant="globex").get_one_response(GLOBEX_CONTACT_ID)
    assert owner.status_code == 200, (
        "globex cannot read its own contact, so the 404 above may be a missing "
        "row rather than tenant isolation working"
    )


@pytest.mark.readonly
@allure.feature("Tenant isolation")
@allure.story("Another tenant's segment and campaign are not found")
@pytest.mark.parametrize(
    ("what", "path", "own_id", "other_id"),
    [
        ("segment", "/api/segments", SEGMENT_ENTERPRISE_RULE, SEGMENT_GLOBEX_FREE),
        ("campaign", "/api/campaigns", CAMPAIGN_DRAFT, CAMPAIGN_GLOBEX_DRAFT),
    ],
)
def test_another_tenants_records_read_as_not_found(api, what, path, own_id, other_id):
    """The same 404-not-403 rule as contacts, across the other two modules.

    Isolation implemented per-endpoint tends to be implemented per-endpoint
    *inconsistently* — one router remembers to scope its query and the next one
    does not. Each case carries its own control read so a blanket 404 cannot
    pass for security.
    """
    acme = api.raw(tenant="acme")

    own = acme.get(f"{path}/{own_id}")
    assert own.status_code == 200, f"the control read of acme's own {what} failed"

    other = acme.get(f"{path}/{other_id}")
    assert other.status_code == 404, (
        f"acme read globex's {what} with status {other.status_code}; 403 would "
        f"confirm the id exists and leak globex's id space"
    )

    owner = api.raw(tenant="globex").get(f"{path}/{other_id}")
    assert owner.status_code == 200, (
        f"globex cannot read its own {what}, so the 404 above may be a missing "
        f"row rather than isolation working"
    )


@allure.feature("Tenant isolation")
@allure.story("A campaign cannot target another tenant's segment")
def test_a_campaign_cannot_target_another_tenants_segment(api):
    """A write that would create a cross-tenant reference, refused at the point
    of creation rather than discovered later when the campaign resolves to an
    audience it should never have seen.
    """
    response = api.campaigns(tenant="acme").create_response(
        campaign_payload(segment_id=SEGMENT_GLOBEX_FREE)
    )

    assert response.status_code == 404, (
        f"an acme campaign was allowed to target globex's segment "
        f"({response.status_code})"
    )


@allure.feature("Tenant isolation")
@allure.story("Segment membership never crosses the tenant boundary")
def test_a_static_segment_cannot_pull_in_another_tenants_contact(api):
    """The subtle one.

    A static segment is just a list of ids, and nothing stops an acme user
    writing globex's contact id into it. The protection cannot live in the
    segment — it has to live in how membership is resolved, which is scoped to
    the caller's tenant. So the segment is allowed to hold the id, and the id
    simply never resolves to a contact.
    """
    own = api.contacts(tenant="acme").create(contact_payload())
    try:
        segment = api.segments(tenant="acme").create(
            static_segment_payload([own.id, GLOBEX_CONTACT_ID])
        )
        members = api.segments(tenant="acme").members(segment.id)
        member_ids = {contact.id for contact in members}

        assert own.id in member_ids, "the segment did not resolve its own tenant's contact"
        assert GLOBEX_CONTACT_ID not in member_ids, (
            "an acme segment listing a globex contact id resolved to that "
            "contact — membership is not tenant-scoped"
        )
        assert {contact.tenant_id for contact in members} == {"acme"}
    finally:
        api.contacts(tenant="acme").delete_one_response(own.id)
