"""What the interface does when the API misbehaves.

These are the states that never occur while everything works, which is exactly
why they are never noticed until they occur in front of someone. A server error,
a request that never returns, a response whose shape is wrong — none can be
produced by driving the application normally, and none would be covered by any
amount of happy-path clicking.

`route.fulfill` and `route.abort` let the test *be* the failing server. The
assertion is never merely "it did not crash": a blank table is not a crash
either, and is worse than an error message because the reader concludes there is
no data rather than that something went wrong.

Every route is intercepted before navigation, and scoped to one endpoint so the
session restore on page load is untouched.
"""

import json

import allure
import pytest

from pages.analytics_page import AnalyticsPage
from pages.contacts_page import ContactsPage

pytestmark = [pytest.mark.ui]

CONTACTS_ENDPOINT = "**/api/contacts?*"


@allure.feature("Error states")
@allure.story("A server error is reported, not swallowed")
def test_a_server_error_is_shown_in_the_grid(page, settings):
    """500 from the list endpoint.

    The grid must say something. The failure mode this guards against is the
    table rendering empty — indistinguishable, to a reader, from a tenant that
    genuinely has no contacts.
    """
    page.route(
        CONTACTS_ENDPOINT,
        lambda route: route.fulfill(
            status=500,
            content_type="application/json",
            body=json.dumps({"detail": "Database is on fire"}),
        ),
    )

    contacts = ContactsPage(page, settings)
    contacts.open_with()

    contacts.expect_visible(contacts.grid.error_message)
    contacts.expect_contains_text(contacts.grid.error_message, "Database is on fire")
    contacts.expect_hidden(contacts.grid.empty_message)


@allure.feature("Error states")
@allure.story("A request that never returns does not hang the interface")
def test_a_timed_out_request_reports_that_the_api_is_unreachable(page, settings):
    """The request is aborted as a timeout, which is what the browser sees when
    a server accepts a connection and then never answers.

    The distinction that matters is between "the API said no" and "the API said
    nothing" — the second is an infrastructure problem, and telling the reader so
    is the difference between a useful message and a misleading one.
    """
    page.route(CONTACTS_ENDPOINT, lambda route: route.abort("timedout"))

    contacts = ContactsPage(page, settings)
    contacts.open_with()

    contacts.expect_visible(contacts.grid.error_message)
    contacts.expect_contains_text(contacts.grid.error_message, "Cannot reach the API")


@allure.feature("Error states")
@allure.story("An empty result is a state, not a failure")
def test_an_empty_result_shows_the_empty_state_not_an_error(page, settings):
    """A well-formed response with nothing in it.

    Worth its own test because "no rows" and "broken" render almost the same
    way if nobody designed the difference, and the application must not present
    an ordinary empty tenant as something being wrong.
    """
    page.route(
        CONTACTS_ENDPOINT,
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"items": [], "total": 0, "page": 1, "size": 20}),
        ),
    )

    contacts = ContactsPage(page, settings)
    contacts.open_with()
    contacts.grid.expect_loaded()

    contacts.expect_visible(contacts.grid.empty_message)
    contacts.expect_hidden(contacts.grid.error_message)
    assert contacts.grid.total() == 0


@allure.feature("Error states")
@allure.story("A malformed payload degrades instead of blanking")
def test_a_malformed_payload_is_reported_rather_than_rendered(page, settings):
    """200 OK, with a body that is not the shape the client expects.

    This is the failure a contract test predicts and a functional test never
    reaches: the status is fine, so nothing in the request path complains, and
    the client walks into a field that is not there. The interface has to end up
    somewhere a reader can understand rather than half-rendered.
    """
    page.route(
        CONTACTS_ENDPOINT,
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"unexpected": "shape", "no_items_key": True}),
        ),
    )

    contacts = ContactsPage(page, settings)
    contacts.open_with()

    # Something must be said, and the table must not be left showing its
    # "Loading…" placeholder forever.
    contacts.expect_visible(contacts.grid.error_message)
    contacts.expect_hidden(contacts.page.get_by_text("Loading…"))


@allure.feature("Error states")
@allure.story("A failing dashboard says so rather than showing a blank page")
def test_a_failing_analytics_request_shows_an_error_page(page, settings):
    """Analytics has no error handling of its own — it lets the failure reach the
    router, which renders a message rather than leaving an empty outlet.

    That is a legitimate design (one handler, one place to change) and it is
    worth a test precisely because it depends on something outside the view: if
    the router's catch were ever removed, this screen would silently go blank.
    """
    page.route(
        "**/api/analytics/overview",
        lambda route: route.fulfill(
            status=500,
            content_type="application/json",
            body=json.dumps({"detail": "analytics unavailable"}),
        ),
    )

    analytics = AnalyticsPage(page, settings)
    analytics.open("/analytics")

    analytics.expect_visible("route-error")
    analytics.expect_contains_text("route-error", "analytics unavailable")
