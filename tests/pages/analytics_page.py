"""The analytics dashboard."""

from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class AnalyticsPage(BasePage):
    """Wraps #/analytics.

    Deliberately thin on chart internals. The tests here assert on the payload
    behind the chart rather than on rendered geometry, so this exposes the
    values the application printed as text — never a bar's width.
    """

    OVERVIEW_ENDPOINT = "**/api/analytics/overview"

    def __init__(self, page, settings) -> None:
        super().__init__(page, settings)

    def open_dashboard(self) -> None:
        self.open("/analytics")
        self.expect_visible("analytics-view")

    def open_table_view(self) -> None:
        """The table twin of every chart, reachable by link."""
        self.open("/analytics?view=table")
        self.expect_visible("analytics-view")

    # --- values, as text ---------------------------------------------------

    def stat(self, name: str) -> Locator:
        return self.testid(f"stat-{name}")

    def stat_value(self, name: str) -> int:
        """The number the tile displays, read from the data attribute rather
        than the formatted label — formatting is presentation and may add
        separators; the value is the thing under test."""
        raw = self.stat(name).locator(".stat-value").get_attribute("data-value")
        return int(raw)

    def campaign_card(self, campaign_id: int) -> Locator:
        return self.testid(f"analytics-campaign-{campaign_id}")

    def rates_text(self, campaign_id: int) -> str:
        return self.testid(f"analytics-rates-{campaign_id}").inner_text()
