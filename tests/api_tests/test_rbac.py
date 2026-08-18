"""Role-based access control at the API layer."""

import allure
import pytest

from data.factories import contact_payload

pytestmark = [pytest.mark.api, pytest.mark.smoke]


@allure.feature("Authorisation")
@allure.story("A viewer cannot create contacts")
def test_viewer_cannot_create_a_contact(api):
    """403, and — the part a status-code assertion would miss — no contact.

    An endpoint that rejects the response but has already committed the row is
    a real failure mode, and it looks identical to a correct one from the
    status code alone. So the test also asks, as an admin, whether the record
    exists. Searching by the unique email means the answer cannot be confused
    by anything another worker created.
    """
    payload = contact_payload()

    with allure.step("Attempt the create as a viewer"):
        response = api.contacts(role="viewer").create_response(payload)

    assert response.status_code == 403, "a viewer must not be allowed to create contacts"

    with allure.step("Confirm as an admin that nothing was written"):
        found = api.contacts(role="admin").list(q=payload["email"])

    assert found.total == 0, (
        f"the create was refused with 403 but {payload['email']} exists anyway — "
        f"the rejection happened after the write"
    )
