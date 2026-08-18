"""Segments: the list, and the editor with its rule builder."""

from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage
from pages.components.confirm_dialog import ConfirmDialog
from pages.components.data_grid import DataGrid
from pages.components.rule_builder import RuleBuilder


class SegmentsPage(BasePage):
    """Wraps #/segments and #/segments/{id}."""

    def __init__(self, page, settings) -> None:
        super().__init__(page, settings)
        self.grid = DataGrid(page, settings, "segments")
        self.rules = RuleBuilder(page, settings)
        self.dialog = ConfirmDialog(page)

    def open_list(self) -> None:
        self.open("/segments")
        self.expect_visible("segments-view")

    def open_editor(self, segment_id: int) -> None:
        """The editor is a route, so it is deep-linkable."""
        self.open(f"/segments/{segment_id}")
        self.expect_visible("segment-editor")

    @property
    def name_input(self) -> Locator:
        return self.testid("segment-name")

    @property
    def save_button(self) -> Locator:
        return self.testid("segment-save")

    @property
    def error(self) -> Locator:
        return self.testid("segment-error")

    def members_link(self, segment_id: int) -> Locator:
        return self.testid(f"segment-members-{segment_id}")
