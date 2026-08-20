"""Contacts: the full write path, and the ways it should refuse.

Each test creates the contact it operates on, with a UUID-stamped email, so
nothing here reads or mutates a row another worker might be using.
"""

import allure
import pytest

from data.factories import contact_payload, unique_email

pytestmark = [pytest.mark.api]


@pytest.fixture
def contact(api):
    """A contact belonging to this test alone, removed afterwards."""
    contacts = api.contacts()
    created = contacts.create(contact_payload())
    yield created
    contacts.delete_one_response(created.id)


@allure.feature("Contacts")
@allure.story("A created contact reads back as it was sent")
def test_a_created_contact_reads_back_with_the_values_it_was_given(api):
    """The round trip, including the JSON attributes — the field most likely to
    be quietly dropped, since it is the only one that is not a plain column.
    """
    payload = contact_payload(country="GB", plan="enterprise")
    contacts = api.contacts()

    created = contacts.create(payload)
    try:
        assert created.email == payload["email"]
        assert created.country == "GB"
        assert created.plan == "enterprise"
        assert created.attributes == payload["attributes"], (
            "the attributes JSON did not survive the round trip"
        )

        fetched = contacts.get_one(created.id)
        assert fetched.model_dump() == created.model_dump(), (
            "reading the contact back gave something different from the create "
            "response"
        )
    finally:
        contacts.delete_one_response(created.id)


@allure.feature("Contacts")
@allure.story("A partial update changes only what was sent")
def test_an_update_changes_only_the_fields_it_names(api, contact):
    """PATCH means partial. An implementation that rebuilt the row from the body
    would blank every field the caller left out, and the response to *this*
    request would still look correct.
    """
    before = api.contacts().get_one(contact.id)

    updated = api.contacts().update(contact.id, {"plan": "enterprise"})

    assert updated.plan == "enterprise"
    assert updated.email == before.email, "email was changed by an update that did not mention it"
    assert updated.first_name == before.first_name
    assert updated.last_name == before.last_name
    assert updated.country == before.country
    assert updated.attributes == before.attributes, (
        "the attributes JSON was cleared by an update that did not mention it"
    )


@allure.feature("Contacts")
@allure.story("A deleted contact is gone")
def test_a_deleted_contact_is_no_longer_found(api):
    contacts = api.contacts()
    created = contacts.create(contact_payload())

    contacts.delete_one(created.id)

    assert contacts.get_one_response(created.id).status_code == 404, (
        "the contact was still readable after a successful delete"
    )
    assert contacts.list(q=created.email).total == 0, (
        "the contact no longer reads by id but still appears in listings"
    )


@allure.feature("Contacts")
@allure.story("A duplicate email is refused")
def test_a_duplicate_email_is_refused(api, contact):
    """409, not 500. A unique-constraint violation reaching the client as a
    server error would be the application failing to own a rule it declared.
    """
    response = api.contacts().create_response(contact_payload(email=contact.email))

    assert response.status_code == 409, (
        f"creating a second contact with an existing email returned "
        f"{response.status_code}"
    )


@allure.feature("Contacts")
@allure.story("A malformed email is rejected before it is stored")
def test_a_malformed_email_is_rejected(api):
    """Validation, not storage: nothing should reach the database to be found
    later by whoever wonders why the mailing list has "not-an-email" in it.
    """
    payload = contact_payload(email="not-an-email")

    response = api.contacts().create_response(payload)

    assert response.status_code == 422
    assert api.contacts().list(q="not-an-email").total == 0, (
        "the invalid address was rejected but stored anyway"
    )


@allure.feature("Contacts")
@allure.story("Country must be a two-letter code")
@pytest.mark.parametrize("country", ["U", "USA", ""])
def test_a_country_that_is_not_two_letters_is_rejected(api, country):
    """The field is declared as exactly two characters, so both a shorter and a
    longer value have to fail — a bound checked on one side only is a common
    and invisible mistake.
    """
    response = api.contacts().create_response(
        contact_payload(email=unique_email("country"), country=country)
    )

    assert response.status_code == 422, (
        f"country={country!r} was accepted; the field is meant to be a "
        f"two-letter code"
    )


@allure.feature("Contacts")
@allure.story("A contact that has deliveries cannot be deleted")
def test_a_contact_with_deliveries_cannot_be_deleted(api, sent_campaign):
    """The regression test for DEF-001.

    A contact referenced by a delivery must not be removable, and the refusal
    has to be a conflict rather than a server error. The distinction is not
    cosmetic: 500 with a body of "Internal Server Error" tells the caller
    nothing about why, is indistinguishable from a genuine fault in monitoring,
    and — under CI's request density — did not reliably produce a response at
    all, which is how it became DEF-004.

    The second assertion is the one with teeth. A refusal that had already
    committed the delete would look identical from the status code alone.
    """
    campaign, deliveries = sent_campaign
    contact_id = deliveries[0].contact_id
    contacts = api.contacts()

    with allure.step(f"Attempt to delete contact {contact_id}, which has a delivery"):
        response = contacts.delete_one_response(contact_id)

    assert response.status_code == 409, (
        f"deleting a contact with deliveries returned {response.status_code}; "
        f"a referenced row must be refused as a conflict, not raised as a "
        f"server error"
    )

    with allure.step("The contact is still there"):
        assert contacts.get_one_response(contact_id).status_code == 200, (
            "the delete was refused but the contact is gone anyway"
        )
