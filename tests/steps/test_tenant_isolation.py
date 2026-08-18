"""Steps for the tenant isolation journey."""

from __future__ import annotations

import pytest
from pytest_bdd import parsers, scenarios, then, when

from data.constants import CAMPAIGN_GLOBEX_DRAFT, GLOBEX_CONTACT_ID

pytestmark = [pytest.mark.e2e, pytest.mark.api]

scenarios("../features/tenant_isolation.feature")

# The feature file speaks about "a customer" and "a campaign"; which endpoint
# and which seeded record that means is a detail the reader does not need.
RECORDS = {
    "customer": ("/api/contacts", GLOBEX_CONTACT_ID),
    "campaign": ("/api/campaigns", CAMPAIGN_GLOBEX_DRAFT),
}


@when(parsers.parse('I ask for a {record} belonging to "{owner}"'))
def i_ask_for_another_tenants_record(journey, api, record, owner):
    path, record_id = RECORDS[record]
    journey.record = (path, record_id, owner)
    journey.outcome = api.raw(role=journey.role, tenant=journey.tenant).get(
        f"{path}/{record_id}"
    )


@then("it appears not to exist")
def it_appears_not_to_exist(journey):
    """404, and specifically not 403.

    Both refuse the request, so both look secure. But "forbidden" confirms the
    record is there, and confirming that is itself a disclosure: anyone could
    walk the identifiers and learn how many customers the other organisation
    has.
    """
    assert journey.outcome.status_code == 404, (
        f"got {journey.outcome.status_code}; a refusal that admits the record "
        f"exists tells the asker something they should not learn"
    )


@then("its owner can still see it")
def its_owner_can_still_see_it(journey, api):
    """The control. Without it, an endpoint broken for everybody would pass."""
    path, record_id, owner = journey.record
    response = api.raw(role="admin", tenant=owner).get(f"{path}/{record_id}")
    assert response.status_code == 200, (
        f"{owner} cannot see its own {path.rsplit('/', 1)[-1]}, so the refusal "
        f"above may be a missing record rather than isolation working"
    )
