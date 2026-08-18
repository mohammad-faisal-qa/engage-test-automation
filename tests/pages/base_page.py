"""The behaviour every page object shares.

Two rules are enforced here rather than left to each page:

**Locate by `data-testid`.** The application puts one on every interactive
element for exactly this reason. CSS classes and text move when someone restyles
a button or rewords a label, and a test that broke because a button turned blue
is a test nobody trusts.

**Wait for a condition, never for a duration.** Playwright's locators already
auto-wait for actionability, so the helpers here add assertions about state
rather than sleeps. There is no `time.sleep` in this package.
"""

from __future__ import annotations

from playwright.sync_api import Locator, Page, expect


class BasePage:
    """A page object over one Playwright page."""

    def __init__(self, page: Page, settings) -> None:
        self.page = page
        self.settings = settings

    # --- navigation --------------------------------------------------------

    @property
    def base_url(self) -> str:
        return self.settings.web_base_url.rstrip("/")

    def open(self, route: str = "/") -> None:
        """Navigate straight to a hash route.

        The application uses hash routing, so any state reachable by clicking is
        also reachable by URL. Going directly is faster than clicking there and,
        more importantly, it makes the test independent of the path taken — a
        broken nav link should fail the nav test, not every test downstream of it.
        """
        self.page.goto(f"{self.base_url}/#{route}", wait_until="domcontentloaded")

    # --- locating ----------------------------------------------------------

    def testid(self, name: str) -> Locator:
        """The only locator strategy this suite uses."""
        return self.page.get_by_test_id(name)

    # --- waiting -----------------------------------------------------------

    def expect_visible(self, name: str, *, timeout: float | None = None) -> Locator:
        locator = self.testid(name)
        expect(locator).to_be_visible(timeout=self._timeout(timeout))
        return locator

    def expect_hidden(self, name: str, *, timeout: float | None = None) -> None:
        expect(self.testid(name)).to_be_hidden(timeout=self._timeout(timeout))

    def expect_text(self, name: str, text: str, *, timeout: float | None = None) -> None:
        expect(self.testid(name)).to_have_text(text, timeout=self._timeout(timeout))

    def expect_route(self, route: str, *, timeout: float | None = None) -> None:
        """Assert the hash route, ignoring whatever precedes it."""
        self.page.wait_for_url(f"**/#{route}", timeout=self._timeout(timeout))

    def _timeout(self, timeout: float | None) -> float:
        """Milliseconds, from the suite's own seconds-based settings."""
        seconds = self.settings.poll_timeout if timeout is None else timeout
        return seconds * 1000
