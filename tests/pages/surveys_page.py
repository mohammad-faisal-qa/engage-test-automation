"""Onsite surveys: the list and the question builder."""

from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage
from pages.components.data_grid import DataGrid


class SurveysPage(BasePage):
    """Wraps #/surveys."""

    def __init__(self, page, settings) -> None:
        super().__init__(page, settings)
        self.grid = DataGrid(page, settings, "surveys")

    def open_list(self) -> None:
        self.open("/surveys")
        self.expect_visible("surveys-view")

    def open_editor(self, survey_id: int) -> None:
        self.open(f"/surveys/{survey_id}")
        self.expect_visible("survey-editor")

    def question_row(self, index: int) -> Locator:
        return self.testid(f"question-row-{index}")

    def add_question(self) -> None:
        self.testid("survey-add-question").click()

    @property
    def error(self) -> Locator:
        return self.testid("survey-error")
