"""The contacts grid: paging, search, filters and URL state.

Grid state lives entirely in the URL, which is the single most useful thing
about this screen from a testing point of view. Reaching "page 3 of a search for
aisha" by clicking is four interactions, each of which can fail for its own
reasons and each of which has to be waited on. As a link it is one navigation,
and it is what sharing the URL would do anyway — so the deep link is both the
faster path and the more faithful one.

Assertions are relative wherever a count could move. Another worker creating a
contact between two requests must not fail a test about paging.
"""

import allure
import pytest

from data.constants import DEFAULT_PAGE_SIZE
from pages.contacts_page import ContactsPage

pytestmark = [pytest.mark.ui]


@allure.feature("Contacts grid")
@allure.story("A deep link opens the grid at that page")
def test_a_deep_link_opens_the_grid_at_a_given_page(page, settings):
    """Page size 10 rather than the default 20, so there are enough pages for
    "page 3" to be a real page for acme's forty seeded contacts."""
    contacts = ContactsPage(page, settings)

    with allure.step("Open #/contacts?page=3&size=10 directly"):
        contacts.open_with(page=3, size=10)
        contacts.grid.expect_loaded()

    contacts.expect_contains_text(contacts.grid.page_info, "Page 3")
    assert "page=3" in page.url

    ids = contacts.grid.row_ids()
    assert ids, "page 3 of the seeded contacts should not be empty"
    assert len(ids) <= 10, f"a page of size 10 returned {len(ids)} rows"

    # The third page of size ten cannot contain a record from the first ten,
    # whatever the seed holds — a relative claim that no concurrent insert can
    # break, unlike asserting the specific ids.
    contacts.open_with(page=1, size=10)
    contacts.grid.expect_loaded()
    assert not set(ids) & set(contacts.grid.row_ids()), (
        "page 3 and page 1 shared records"
    )


@allure.feature("Contacts grid")
@allure.story("Pages contain different records")
def test_consecutive_pages_show_different_records(page, settings):
    contacts = ContactsPage(page, settings)

    contacts.open_with(page=1, size=10)
    contacts.grid.expect_loaded()
    first = contacts.grid.row_ids()

    contacts.open_with(page=2, size=10)
    contacts.grid.expect_loaded()
    second = contacts.grid.row_ids()

    assert first and second
    assert not set(first) & set(second), (
        f"pages 1 and 2 share records {sorted(set(first) & set(second))}, so "
        f"someone walking the grid would see them twice"
    )


@allure.feature("Contacts grid")
@allure.story("A deep link applies a search term")
def test_a_deep_link_applies_a_search_term(page, settings, api):
    """The search box is reached by its label, the way a person finds it — and
    the term arrives from the URL, proving the grid reads its state from there
    rather than only from the control.
    """
    contacts = ContactsPage(page, settings)

    with allure.step("Open a searched grid directly"):
        contacts.open_with(q="aisha")
        contacts.grid.expect_loaded()

    assert contacts.search_box.input_value() == "aisha", (
        "the search box did not reflect the term in the URL"
    )

    ids = contacts.grid.row_ids()
    assert ids, "the seeded data should contain at least one Aisha"

    # Cross-checked against the API rather than against a hardcoded number, so
    # the assertion survives a change to the seed.
    expected = {c.id for c in api.contacts().list(q="aisha", size=100).items}
    assert set(ids) <= expected, (
        f"the grid showed {sorted(set(ids) - expected)}, which the API does not "
        f"return for the same search"
    )


@allure.feature("Contacts grid")
@allure.story("Filters narrow the grid and land in the URL")
def test_filters_narrow_the_grid(page, settings):
    contacts = ContactsPage(page, settings)
    contacts.open_grid()

    with allure.step("Filter by country"):
        contacts.filter_country("GB")
        contacts.grid.expect_loaded()

    assert "country=GB" in page.url, (
        "the filter did not reach the URL, so the filtered view is not shareable"
    )

    with allure.step("Every visible row matches the filter"):
        countries = contacts.grid.body.locator("td:nth-child(5)").all_inner_texts()
    assert set(countries) == {"GB"}, f"expected only GB rows, saw {sorted(set(countries))}"


@allure.feature("Contacts grid")
@allure.story("Paging controls move between pages and stop at the ends")
def test_paging_controls_move_and_stop_at_the_ends(page, settings):
    contacts = ContactsPage(page, settings)

    contacts.open_with(size=10)
    contacts.grid.expect_loaded()

    from playwright.sync_api import expect

    expect(contacts.grid.previous_button).to_be_disabled()
    first = contacts.grid.row_ids()

    with allure.step("Next moves forward"):
        contacts.grid.next_page()
        contacts.grid.expect_page(2)
    assert contacts.grid.row_ids() != first
    expect(contacts.grid.previous_button).to_be_enabled()

    with allure.step("Previous comes back"):
        contacts.grid.previous_page()
        contacts.grid.expect_page(1)
    assert contacts.grid.row_ids() == first


@allure.feature("Contacts grid")
@allure.story("The back button restores the previous grid state")
def test_the_back_button_returns_to_the_previous_grid_state(page, settings):
    """State in the URL is only worth having if history works with it."""
    contacts = ContactsPage(page, settings)

    contacts.open_with(size=10)
    contacts.grid.expect_loaded()
    first_page_ids = contacts.grid.row_ids()

    contacts.grid.next_page()
    contacts.grid.expect_page(2)
    assert contacts.grid.row_ids() != first_page_ids

    with allure.step("Go back"):
        contacts.back()
        contacts.grid.expect_page(1)

    assert contacts.grid.row_ids() == first_page_ids, (
        "the back button did not restore the previous page of the grid"
    )


@allure.feature("Contacts grid")
@allure.story("A search with no matches shows an empty state")
def test_a_search_with_no_matches_shows_the_empty_state(page, settings):
    """Empty is a state to design for, not an error. The distinction matters:
    a blank table looks identical to a broken one.
    """
    contacts = ContactsPage(page, settings)

    contacts.open_with(q="zzz-no-such-contact-zzz")
    contacts.grid.expect_loaded()

    contacts.expect_visible(contacts.grid.empty_message)
    contacts.expect_contains_text(contacts.grid.empty_message, "No contacts match")
    assert contacts.grid.total() == 0


@allure.feature("Contacts grid")
@allure.story("Page size changes how many rows are returned")
def test_changing_the_page_size_changes_the_rows_shown(page, settings):
    contacts = ContactsPage(page, settings)

    contacts.open_grid()
    assert len(contacts.grid.row_ids()) <= DEFAULT_PAGE_SIZE

    with allure.step("Switch to ten rows per page"):
        contacts.set_page_size(10)
        contacts.grid.expect_row_count(10)

    assert len(contacts.grid.row_ids()) == 10
    assert "size=10" in page.url
