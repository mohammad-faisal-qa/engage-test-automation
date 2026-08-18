"""The seeded facts this suite depends on, checked against the application.

`data/constants.py` is a set of claims about the application's seed data —
that contact 41 belongs to globex, that campaign 3 is the sent one. Those claims
are load-bearing: tenant isolation, RBAC and every Phase 2 test built on them
reads correctly only if they are true.

Nothing enforces them. The seed lives in another repository now, and a rename or
a reordering there would leave these constants quietly wrong. The failures that
follow would be scattered and misleading — `test_a_contact_from_another_tenant`
failing because the id it uses stopped belonging to the other tenant, reported as
a tenant-isolation bug in an application that is behaving perfectly.

So this file exists to fail *first* and *once*, naming the drift for what it is.
Every check here is read-only, so it is safe in parallel and against a shared
environment.
"""

import allure
import pytest

from data.constants import (
    ACME_CONTACT_ID,
    CAMPAIGN_DRAFT,
    CAMPAIGN_GLOBEX_DRAFT,
    CAMPAIGN_GLOBEX_RUNNING,
    CAMPAIGN_SCHEDULED,
    CAMPAIGN_SENT,
    DEFAULT_PAGE_SIZE,
    GLOBEX_CONTACT_ID,
    MAX_PAGE_SIZE,
    SEGMENT_ENTERPRISE_RULE,
    SEGMENT_GLOBEX_FREE,
    SEGMENT_HIGH_VALUE_RULE,
    SEGMENT_VIP_STATIC,
)

pytestmark = [pytest.mark.api]


@allure.feature("Seed data")
@allure.story("The contact ids the suite hardcodes belong to the tenants it assumes")
@pytest.mark.parametrize(
    ("constant_name", "contact_id", "tenant"),
    [
        ("ACME_CONTACT_ID", ACME_CONTACT_ID, "acme"),
        ("GLOBEX_CONTACT_ID", GLOBEX_CONTACT_ID, "globex"),
    ],
)
def test_seeded_contact_belongs_to_the_tenant_its_constant_names(
    api, constant_name, contact_id, tenant
):
    """Read each id with a token from the tenant that is supposed to own it.

    This is the pair the tenant-isolation test is built on. If the ranges in the
    seed ever move, that test starts asserting something it does not mean, and
    this one says so plainly instead.
    """
    with allure.step(f"Read contact {contact_id} as {tenant}"):
        contact = api.contacts(tenant=tenant).get_one(contact_id)

    assert contact.tenant_id == tenant, (
        f"{constant_name} = {contact_id}, but that contact belongs to "
        f"{contact.tenant_id!r}, not {tenant!r}. The seed in engage-app has moved "
        f"and data/constants.py no longer describes it."
    )


@allure.feature("Seed data")
@allure.story("The seeded segments are the kind and tenant the constants claim")
@pytest.mark.parametrize(
    ("constant_name", "segment_id", "tenant", "kind"),
    [
        ("SEGMENT_ENTERPRISE_RULE", SEGMENT_ENTERPRISE_RULE, "acme", "rule"),
        ("SEGMENT_HIGH_VALUE_RULE", SEGMENT_HIGH_VALUE_RULE, "acme", "rule"),
        ("SEGMENT_VIP_STATIC", SEGMENT_VIP_STATIC, "acme", "static"),
        ("SEGMENT_GLOBEX_FREE", SEGMENT_GLOBEX_FREE, "globex", "rule"),
    ],
)
def test_seeded_segment_matches_its_constant(
    api, constant_name, segment_id, tenant, kind
):
    """The names encode two claims — the tenant and the kind — so check both.

    `SEGMENT_VIP_STATIC` pointing at a rule segment would be the expensive one:
    the Phase 2 evaluator tests would be exercising rule evaluation while
    believing they were covering static membership.
    """
    response = api.raw(tenant=tenant).get(f"/api/segments/{segment_id}", expect=200)
    segment = response.json()

    assert segment["tenant_id"] == tenant, (
        f"{constant_name} = {segment_id} is owned by {segment['tenant_id']!r}, "
        f"not {tenant!r}"
    )
    assert segment["kind"] == kind, (
        f"{constant_name} = {segment_id} is a {segment['kind']!r} segment, but its "
        f"name claims {kind!r}"
    )


@allure.feature("Seed data")
@allure.story("The seeded campaigns are in the states the constants name")
@pytest.mark.parametrize(
    ("constant_name", "campaign_id", "tenant", "status"),
    [
        ("CAMPAIGN_DRAFT", CAMPAIGN_DRAFT, "acme", "draft"),
        ("CAMPAIGN_SCHEDULED", CAMPAIGN_SCHEDULED, "acme", "scheduled"),
        ("CAMPAIGN_SENT", CAMPAIGN_SENT, "acme", "sent"),
        ("CAMPAIGN_GLOBEX_DRAFT", CAMPAIGN_GLOBEX_DRAFT, "globex", "draft"),
        ("CAMPAIGN_GLOBEX_RUNNING", CAMPAIGN_GLOBEX_RUNNING, "globex", "running"),
    ],
)
def test_seeded_campaign_is_in_the_state_its_constant_names(
    api, constant_name, campaign_id, tenant, status
):
    """One campaign per interesting state, which is what the state-machine tests
    in Phase 2 will select from. A constant pointing at the wrong state would
    make "reject draft -> sent" pass or fail for reasons unrelated to the rule.
    """
    response = api.raw(tenant=tenant).get(f"/api/campaigns/{campaign_id}", expect=200)
    campaign = response.json()

    assert campaign["tenant_id"] == tenant, (
        f"{constant_name} = {campaign_id} is owned by {campaign['tenant_id']!r}, "
        f"not {tenant!r}"
    )
    assert campaign["status"] == status, (
        f"{constant_name} = {campaign_id} is {campaign['status']!r}, but its name "
        f"claims {status!r}"
    )


@allure.feature("Seed data")
@allure.story("The pagination constants match the API's actual contract")
def test_pagination_constants_match_the_api_contract(api):
    """These two are a different kind of claim: not seeded rows, but the
    application's declared limits. They are asserted the way a caller would
    discover them — by asking for the boundary and one past it.
    """
    contacts = api.contacts()

    with allure.step("Omit size entirely and read the server's default"):
        default_page = contacts.list()
    assert default_page.size == DEFAULT_PAGE_SIZE, (
        f"DEFAULT_PAGE_SIZE = {DEFAULT_PAGE_SIZE}, but the API defaults to "
        f"{default_page.size}"
    )

    with allure.step(f"Ask for exactly MAX_PAGE_SIZE ({MAX_PAGE_SIZE})"):
        at_limit = contacts.list_response(size=MAX_PAGE_SIZE)
    assert at_limit.status_code == 200, (
        f"MAX_PAGE_SIZE = {MAX_PAGE_SIZE} was rejected with "
        f"{at_limit.status_code}, so it is not the maximum"
    )

    with allure.step(f"Ask for one more than the maximum ({MAX_PAGE_SIZE + 1})"):
        past_limit = contacts.list_response(size=MAX_PAGE_SIZE + 1)
    assert past_limit.status_code == 422, (
        f"size={MAX_PAGE_SIZE + 1} returned {past_limit.status_code}; the cap is "
        f"not where MAX_PAGE_SIZE says it is"
    )
