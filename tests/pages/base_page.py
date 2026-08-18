"""The behaviour every page object shares.

Locator hierarchy, in order of preference:

1. **User-facing** — `get_by_role`, `get_by_label`, `get_by_placeholder`. These
   assert the thing a person actually uses, so they fail when the experience
   breaks: a button that stops being a button, an input that loses its label.
   That is a defect a `data-testid` lookup would sail straight past.
2. **`data-testid`** where the semantics are ambiguous. Five tables on a page
   are all `role=table`, and "the third row's Delete button" is not something a
   role query says well. The application puts a testid on every interactive
   element precisely so tests do not have to guess.
3. **CSS or XPath** as a last resort, and each use should be uncomfortable
   enough to prompt a testid instead.

Waiting is always for a condition, never a duration. Playwright's locators
auto-wait for actionability; the helpers here add assertions about state. There
is no `time.sleep` in this package.
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
        """Navigate straight to a hash route, query string and all.

        Grid state lives in the URL, so any state reachable by clicking is also
        reachable by link. Going directly is faster and, more importantly, makes
        a test independent of the path taken — a broken filter control should
        fail the filter test, not every test that needed a filtered page.
        """
        self.page.goto(f"{self.base_url}/#{route}", wait_until="domcontentloaded")

    def back(self) -> None:
        self.page.go_back()

    # --- locating ----------------------------------------------------------

    def role(self, role: str, **kwargs) -> Locator:
        """Preferred: how a person (or a screen reader) finds the element."""
        return self.page.get_by_role(role, **kwargs)

    def label(self, text: str, **kwargs) -> Locator:
        return self.page.get_by_label(text, **kwargs)

    def testid(self, name: str) -> Locator:
        """For elements whose role is ambiguous or whose identity is per-row."""
        return self.page.get_by_test_id(name)

    # --- waiting -----------------------------------------------------------

    def expect_visible(self, target: str | Locator, *, timeout: float | None = None) -> Locator:
        locator = self._locator(target)
        expect(locator).to_be_visible(timeout=self._ms(timeout))
        return locator

    def expect_hidden(self, target: str | Locator, *, timeout: float | None = None) -> None:
        expect(self._locator(target)).to_be_hidden(timeout=self._ms(timeout))

    def expect_count(self, target: str | Locator, count: int, *, timeout: float | None = None) -> None:
        expect(self._locator(target)).to_have_count(count, timeout=self._ms(timeout))

    def expect_text(self, target: str | Locator, text, *, timeout: float | None = None) -> None:
        expect(self._locator(target)).to_have_text(text, timeout=self._ms(timeout))

    def expect_contains_text(self, target: str | Locator, text, *, timeout: float | None = None) -> None:
        expect(self._locator(target)).to_contain_text(text, timeout=self._ms(timeout))

    def expect_route(self, route: str, *, timeout: float | None = None) -> None:
        self.page.wait_for_url(f"**/#{route}", timeout=self._ms(timeout))

    def _locator(self, target: str | Locator) -> Locator:
        return self.testid(target) if isinstance(target, str) else target

    def _ms(self, timeout: float | None) -> float:
        seconds = self.settings.poll_timeout if timeout is None else timeout
        return seconds * 1000
