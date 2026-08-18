"""The application shell: navigation and the signed-in identity."""

from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class Nav(BasePage):
    """The top bar, present on every authenticated view.

    Nav links are real anchors, so they are located by role and name — the way
    a person or a screen reader finds them — rather than by testid.
    """

    SECTIONS = ("contacts", "segments", "campaigns", "notifications", "surveys", "analytics")

    def link(self, section: str) -> Locator:
        return self.testid(f"nav-{section}")

    def go_to(self, section: str) -> None:
        self.link(section).click()

    # --- identity ----------------------------------------------------------

    @property
    def user_email(self) -> str:
        return self.testid("current-user").inner_text()

    @property
    def role_name(self) -> str:
        return self.testid("current-role").inner_text()

    @property
    def tenant(self) -> str:
        return self.testid("current-tenant").inner_text()

    def expect_signed_in_as(self, email: str, role: str, tenant: str) -> None:
        self.expect_text("current-user", email)
        self.expect_text("current-role", role)
        self.expect_text("current-tenant", tenant)

    def sign_out(self) -> None:
        self.role("button", name="Sign out").click()
