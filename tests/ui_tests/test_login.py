"""Signing in through the browser.

The only tests in the suite that drive the login form. Everything else starts
from a restored session, which is the point of storage_state — so this is where
the login path itself has to be proven, and it uses `anonymous_page` precisely
so it cannot benefit from the shared state.
"""

import allure
import pytest

from pages.base_page import BasePage
from pages.components.nav import Nav
from pages.login_page import LoginPage

pytestmark = [pytest.mark.ui]


@allure.feature("Login")
@allure.story("Valid credentials sign the user in")
def test_a_valid_login_signs_the_user_in(anonymous_page, settings):
    """Arriving at the grid is not enough on its own.

    The redirect proves routing happened; the header proves the application knows
    *who* arrived. A session restored with a broken token would still redirect,
    and would then show an empty header — which is why both are asserted.
    """
    login = LoginPage(anonymous_page, settings)
    email = settings.user_email("admin", "acme")

    with allure.step(f"Sign in as {email}"):
        login.open()
        login.sign_in(email, settings.seed_password)

    login.expect_text("current-user", email)
    login.expect_text("current-tenant", "acme")
    login.expect_text("current-role", "admin")


@allure.feature("Login")
@allure.story("A wrong password is refused, visibly")
def test_an_invalid_login_shows_an_error(anonymous_page, settings):
    """The failure has to be visible *and* contained.

    Two things go wrong in real login screens: the error is swallowed and the
    form just sits there, or the error shows while the user is signed in anyway.
    So this asserts the message appears, and that the browser stayed on the login
    route with no session established.
    """
    login = LoginPage(anonymous_page, settings)

    with allure.step("Submit a wrong password"):
        login.open()
        login.submit(settings.user_email("admin", "acme"), "definitely-not-the-password")

    with allure.step("The error is shown"):
        login.expect_error("Incorrect email or password.")

    with allure.step("And no session was created"):
        login.expect_route("/login")
        login.expect_hidden("current-user")


@allure.feature("Login")
@allure.story("A restored session needs no login at all")
def test_a_restored_session_lands_signed_in(page, settings):
    """The test that proves storage_state is doing its job.

    It never touches the login form. The browser starts from the shared
    storage-state file — a token in localStorage, exactly what a real returning
    visitor's browser would hold — and the application rehydrates the session
    from it on load.

    Without this, the whole storage_state mechanism would be unexercised: the
    other two tests here deliberately use an anonymous context, so nothing else
    in the suite would notice if the shared state stopped working.
    """
    app = BasePage(page, settings)

    with allure.step("Open the contacts grid directly, with no login"):
        app.open("/contacts")

    app.expect_visible("current-user")
    app.expect_text("current-user", settings.user_email("admin", "acme"))
    app.expect_route("/contacts")
    app.expect_hidden("login-form")


@allure.feature("Login")
@allure.story("An unauthenticated visitor is sent to the login screen")
def test_an_unauthenticated_visitor_is_redirected_to_login(anonymous_page, settings):
    """Deep-linking past the login screen must not work.

    Every route in the application is reachable by URL, which is exactly why the
    guard has to live in the router rather than in the links: hiding a nav item
    does nothing for someone who types the address.
    """
    app = BasePage(anonymous_page, settings)

    with allure.step("Ask for the contacts grid without a session"):
        app.open("/contacts")

    app.expect_route("/login")
    app.expect_visible("login-form")
    app.expect_hidden("current-user")


@allure.feature("Login")
@allure.story("Signing out ends the session")
def test_signing_out_ends_the_session(page, settings):
    """Signing out has to clear the stored token, not merely navigate away.

    The failure worth catching is a sign-out that redirects while leaving the
    token in place: the screen looks right, and the next deep link walks straight
    back in. So this signs out and then tries the door again.
    """
    nav = Nav(page, settings)
    app = BasePage(page, settings)

    app.open("/contacts")
    app.expect_visible("current-user")

    with allure.step("Sign out"):
        nav.sign_out()

    app.expect_route("/login")

    with allure.step("The session is really gone, not just off screen"):
        app.open("/contacts")
        app.expect_route("/login")
        app.expect_hidden("current-user")
