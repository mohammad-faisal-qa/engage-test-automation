"""The segment rule builder: a repeating row of field / operator / value."""

from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class RuleBuilder(BasePage):
    """Conditions inside the segment editor.

    Rows are addressed by index because that is how the markup names them, and
    because the interesting assertions are positional — "the condition I just
    added", "the one left after removing the first".
    """

    def condition_row(self, index: int) -> Locator:
        return self.testid(f"condition-row-{index}")

    def field_select(self, index: int) -> Locator:
        return self.testid(f"condition-field-{index}")

    def operator_select(self, index: int) -> Locator:
        return self.testid(f"condition-op-{index}")

    def value_input(self, index: int) -> Locator:
        return self.testid(f"condition-value-{index}")

    def remove(self, index: int) -> None:
        self.testid(f"condition-remove-{index}").click()

    def add_condition(self) -> None:
        self.testid("segment-add-condition").click()

    def set_condition(self, index: int, *, field: str, operator: str, value: str) -> None:
        self.field_select(index).select_option(field)
        self.operator_select(index).select_option(operator)
        self.value_input(index).fill(value)

    @property
    def condition_count(self) -> int:
        return self.testid("segment-conditions").locator("[data-testid^='condition-row-']").count()

    @property
    def match_mode(self) -> Locator:
        return self.testid("segment-match")

    def set_match(self, mode: str) -> None:
        self.match_mode.select_option(mode)

    # --- preview -----------------------------------------------------------

    def preview(self) -> None:
        self.testid("segment-preview").click()

    @property
    def preview_count(self) -> Locator:
        return self.testid("segment-preview-count")
