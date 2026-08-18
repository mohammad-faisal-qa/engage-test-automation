"""The campaign creation wizard."""

from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage
from pages.components.data_grid import DataGrid
from pages.components.wizard_stepper import WizardStepper


class CampaignWizard(BasePage):
    """Wraps #/campaigns and its five-step creation flow."""

    def __init__(self, page, settings) -> None:
        super().__init__(page, settings)
        self.grid = DataGrid(page, settings, "campaigns")
        self.stepper = WizardStepper(page, settings)

    def open_list(self) -> None:
        self.open("/campaigns")
        self.expect_visible("campaigns-view")

    def start(self) -> None:
        self.testid("campaign-new").click()
        self.expect_visible("campaign-wizard")

    # --- steps -------------------------------------------------------------

    def set_name(self, name: str) -> None:
        self.testid("wizard-name").fill(name)

    def choose_segment(self, segment_id: int | str) -> None:
        self.testid("wizard-segment").select_option(str(segment_id))

    def choose_channel(self, channel: str) -> None:
        self.testid(f"wizard-channel-{channel}").click()

    def send_now(self) -> None:
        self.testid("wizard-when-now").click()

    @property
    def review_name(self) -> Locator:
        return self.testid("review-name")

    @property
    def error(self) -> Locator:
        return self.testid("wizard-error")
