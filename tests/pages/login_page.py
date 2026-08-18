"""The sign-in screen."""

from __future__ import annotations

from pages.base_page import BasePage


class LoginPage(BasePage):
    """Wraps #/login.

    The methods are deliberately split between "do the thing" and "do the thing
    and expect it to work". A test about a *failed* login needs to submit without
    anything asserting success on its behalf, and a test about a successful one
    should not have to spell out what success looks like.
    """

    ROUTE = "/login"

    def open(self, route: str = ROUTE) -> None:
        super().open(route)
        self.expect_visible("login-form")

    # --- actions -----------------------------------------------------------

    def submit(self, email: str, password: str) -> None:
        """Fill the form and submit, asserting nothing about the outcome."""
        self.testid("login-email").fill(email)
        self.testid("login-password").fill(password)
        self.testid("login-submit").click()

    def sign_in(self, email: str, password: str) -> None:
        """Submit and wait to arrive signed in."""
        self.submit(email, password)
        self.expect_signed_in()

    # --- assertions --------------------------------------------------------

    def expect_signed_in(self) -> None:
        """The application redirects to the contacts grid on success, and the
        header carries the identity — so this waits for both the route and the
        evidence, not just the route.
        """
        self.expect_route("/contacts")
        self.expect_visible("current-user")

    def expect_error(self, message: str) -> None:
        self.expect_visible("login-error")
        self.expect_text("login-error", message)

    @property
    def error_text(self) -> str:
        return self.testid("login-error").inner_text()
