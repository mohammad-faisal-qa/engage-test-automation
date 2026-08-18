"""Role-based access control at the API layer."""

import allure
import pytest

from data.factories import contact_payload

pytestmark = [pytest.mark.api]


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


@allure.feature("Authorisation")
@allure.story("An editor can do the thing a viewer cannot")
def test_an_editor_can_create_a_contact(api):
    """The control for every refusal in this file.

    Without it, an endpoint broken for everyone would pass all the negative
    tests — 403 for a viewer looks identical whether the rule is working or the
    route is simply dead.
    """
    contacts = api.contacts(role="editor")
    created = contacts.create(contact_payload())

    try:
        assert created.id
        assert created.tenant_id == "acme"
    finally:
        api.contacts(role="admin").delete_one_response(created.id)


@allure.feature("Authorisation")
@allure.story("A viewer cannot create a segment")
def test_a_viewer_cannot_create_a_segment(api):
    response = api.segments(role="viewer").create_response(
        {"name": "viewer attempt", "kind": "rule", "rules": {"match": "all", "conditions": []}}
    )

    assert response.status_code == 403


@allure.feature("Authorisation")
@allure.story("Deleting is reserved for admins")
def test_an_editor_cannot_delete_a_contact(api):
    """Editors write, admins destroy.

    The interesting part is that the editor *can* create the row and then cannot
    remove it, so this exercises the boundary between two permitted-looking
    operations rather than between permission and none.
    """
    created = api.contacts(role="editor").create(contact_payload())

    try:
        response = api.contacts(role="editor").delete_one_response(created.id)
        assert response.status_code == 403, (
            f"an editor deleted a contact ({response.status_code}); deletion is "
            f"meant to require admin"
        )
        assert api.contacts(role="admin").get_one_response(created.id).status_code == 200, (
            "the delete was refused but the contact is gone anyway"
        )
    finally:
        api.contacts(role="admin").delete_one_response(created.id)


@allure.feature("Authorisation")
@allure.story("A viewer cannot send a campaign")
def test_a_viewer_cannot_send_a_campaign(api, campaign_with_audience):
    """The most consequential refusal in the application: sending is the one
    action with an effect outside the system.
    """
    campaign, _contacts = campaign_with_audience

    response = api.delivery(role="viewer").send_response(campaign.id)

    assert response.status_code == 403
    assert api.campaigns().get_one(campaign.id).status == "draft", (
        "the send was refused but the campaign started running anyway"
    )
    assert api.delivery().deliveries(campaign.id) == [], (
        "the send was refused but deliveries were created"
    )
