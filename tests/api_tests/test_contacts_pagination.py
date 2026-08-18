"""Pagination: the envelope, and that pages actually differ."""

import allure
import pytest

from data.factories import contact_payload

pytestmark = [pytest.mark.api]

PAGE_SIZE = 5


@pytest.mark.smoke
@allure.feature("Contacts")
@allure.story("Paging returns a correct envelope and distinct pages")
def test_contacts_pagination_returns_a_correct_envelope(api):
    """Every assertion here is deliberately relative, never absolute.

    `total == 40` would be the obvious thing to write, and it passes — right up
    until this runs at `-n 4` and another worker inserts a contact between the
    two requests. The suite would then fail on a real system behaving correctly,
    which is the most expensive kind of failure because it trains people to
    rerun rather than to read.

    So: the envelope must echo what was asked for, a page must not exceed the
    size requested, page 2 must contain different records from page 1, and the
    total must be consistent with what was returned. All of those stay true no
    matter what anyone else is doing to the database at the same time.
    """
    contacts = api.contacts()

    with allure.step("Fetch page 1"):
        first = contacts.list(page=1, size=PAGE_SIZE)
    with allure.step("Fetch page 2"):
        second = contacts.list(page=2, size=PAGE_SIZE)

    # The envelope echoes the request.
    assert first.page == 1
    assert second.page == 2
    assert first.size == PAGE_SIZE
    assert second.size == PAGE_SIZE

    # A page never exceeds the size asked for.
    assert len(first.items) <= PAGE_SIZE
    assert len(second.items) <= PAGE_SIZE

    # The seed guarantees enough acme contacts to fill two pages of five;
    # nothing another worker does can reduce that.
    assert len(first.items) == PAGE_SIZE, "not enough seeded contacts to page through"
    assert len(second.items) == PAGE_SIZE

    # The point of paging: page 2 is a different slice, not a repeat of page 1.
    assert first.ids != second.ids
    assert not set(first.ids) & set(second.ids), (
        f"pages overlap: {sorted(set(first.ids) & set(second.ids))} appear on both, "
        f"so a caller walking the pages would see records twice"
    )

    # The total describes the whole collection, so it must be at least what two
    # pages have already produced. A relative check that cannot be broken by a
    # concurrent insert.
    assert first.total >= len(first.items) + len(second.items)

    # Everything returned belongs to the caller's tenant.
    assert {item.tenant_id for item in first.items} == {"acme"}


@allure.feature("Contacts")
@allure.story("Search matches name and email, ignoring case")
def test_search_matches_name_and_email_regardless_of_case(api):
    """Case-insensitivity is the point.

    Postgres `LIKE` is case-sensitive where SQLite's is not, so a search written
    against SQLite behaves differently the moment it is deployed — searching
    "aisha" would stop finding "Aisha". The application uses ILIKE; this is what
    holds it to that.
    """
    contacts = api.contacts()
    created = contacts.create(contact_payload(first_name="Genevieve"))
    try:
        for term in ("Genevieve", "genevieve", "GENEV"):
            with allure.step(f"Search for {term!r}"):
                found = contacts.list(q=term)
            assert created.id in found.ids, f"searching {term!r} did not find the contact"

        by_email = contacts.list(q=created.email)
        assert created.id in by_email.ids, "searching by full email did not find the contact"
    finally:
        contacts.delete_one_response(created.id)


@allure.feature("Contacts")
@allure.story("Filters narrow the collection")
def test_filters_return_only_matching_contacts(api):
    """Asserted as a property of what comes back, never as a count: another
    worker can add a matching contact between the two requests, and a test that
    counted would fail on a system doing exactly the right thing.
    """
    contacts = api.contacts()
    created = contacts.create(contact_payload(country="GB", plan="enterprise"))
    try:
        by_country = contacts.list(country="GB")
        assert {item.country for item in by_country.items} == {"GB"}
        assert created.id in by_country.ids

        by_plan = contacts.list(plan="enterprise")
        assert {item.plan for item in by_plan.items} == {"enterprise"}

        both = contacts.list(country="GB", plan="enterprise")
        assert created.id in both.ids, "the contact vanished when both filters were combined"
    finally:
        contacts.delete_one_response(created.id)


@allure.feature("Contacts")
@allure.story("A page past the end is empty rather than an error")
def test_a_page_beyond_the_last_one_is_empty(api):
    """Running off the end is ordinary paging behaviour, not a failure — a UI
    walking pages should get an empty list and stop, not a 500.
    """
    page = api.contacts().list(page=10_000, size=5)

    assert page.items == []
    assert page.page == 10_000, "the envelope should still echo the page that was asked for"
    assert page.total >= 0


@allure.feature("Contacts")
@allure.story("An invalid page number is rejected")
@pytest.mark.parametrize(("params", "why"), [
    ({"page": 0}, "page numbering starts at 1"),
    ({"page": -1}, "a negative page has no meaning"),
    ({"size": 0}, "a page of nothing is not a page"),
])
def test_invalid_paging_parameters_are_rejected(api, params, why):
    """422 rather than a silent correction. Quietly treating page=0 as page=1
    hides a caller's off-by-one instead of surfacing it.
    """
    response = api.contacts().list_response(**params)

    assert response.status_code == 422, f"{params} was accepted, but {why}"


@allure.feature("Contacts")
@allure.story("Special characters in a search are data, not syntax")
@pytest.mark.parametrize("term", ["%", "_", "'", "100%", "a'b", "%_%"])
def test_special_characters_in_search_are_treated_as_text(api, term):
    """`%` and `_` are wildcards in SQL LIKE and an apostrophe ends a string
    literal. A search for any of them must return a normal response: an
    unescaped wildcard would silently match everything, and an unescaped quote
    is the shape of an injection.
    """
    response = api.contacts().list_response(q=term)

    assert response.status_code == 200, (
        f"searching for {term!r} returned {response.status_code} — the term is "
        f"reaching the query as syntax rather than as data"
    )
    body = response.json()
    assert isinstance(body["items"], list)
