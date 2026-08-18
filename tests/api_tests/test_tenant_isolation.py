"""Multi-tenancy: one tenant's data must be invisible to another."""

import allure
import pytest

from data.constants import ACME_CONTACT_ID, GLOBEX_CONTACT_ID

pytestmark = [pytest.mark.api, pytest.mark.smoke]


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
