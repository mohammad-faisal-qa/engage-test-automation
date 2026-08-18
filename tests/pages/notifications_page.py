"""Onsite notifications: the list, the editor, and the eligibility panel."""

from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage
from pages.components.data_grid import DataGrid


class NotificationsPage(BasePage):
    """Wraps #/notifications.

    The eligibility panel is the interesting part: it evaluates the whole rule
    chain for one contact and reports a verdict, which is what makes frequency
    capping observable without sending anything.
    """

    def __init__(self, page, settings) -> None:
        super().__init__(page, settings)
        self.grid = DataGrid(page, settings, "notifications")

    def open_list(self) -> None:
        self.open("/notifications")
        self.expect_visible("notifications-view")

    def open_editor(self, notification_id: int) -> None:
        self.open(f"/notifications/{notification_id}")
        self.expect_visible("notification-editor")

    # --- eligibility -------------------------------------------------------

    @property
    def eligibility_panel(self) -> Locator:
        return self.testid("eligibility-panel")

    def check_eligibility(self, contact_id: int) -> None:
        self.testid("eligibility-contact").fill(str(contact_id))
        self.testid("eligibility-check").click()

    @property
    def verdict(self) -> Locator:
        return self.testid("eligibility-verdict")
