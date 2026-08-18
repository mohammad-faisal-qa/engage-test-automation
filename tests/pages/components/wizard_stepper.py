"""The campaign wizard's step indicator and navigation."""

from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class WizardStepper(BasePage):
    """Details → Segment → Channel → Schedule → Review.

    The step list is what makes the wizard testable as a state machine rather
    than as a sequence of clicks: `current_step` reads which one the application
    thinks it is on, so a test can assert that a refused Next did not advance.
    """

    STEPS = ("Details", "Segment", "Channel", "Schedule", "Review")

    def step(self, index: int) -> Locator:
        return self.testid(f"wizard-step-{index}")

    @property
    def next_button(self) -> Locator:
        return self.role("button", name="Next")

    @property
    def back_button(self) -> Locator:
        return self.testid("wizard-back")

    @property
    def error(self) -> Locator:
        return self.testid("wizard-error")

    def next(self) -> None:
        self.testid("wizard-next").click()

    def back(self) -> None:
        self.back_button.click()

    def current_step(self) -> int:
        """Index of the step the wizard is showing.

        Read from the class the application marks it with. This is the one place
        a CSS lookup is justified: "active" is a visual state with no role or
        accessible name to query, and the alternative — inferring the step from
        which fields happen to be on screen — would be far more brittle.
        """
        classes = self.testid("wizard-steps").locator("li").evaluate_all(
            "items => items.map(i => i.className)"
        )
        for index, value in enumerate(classes):
            if "is-current" in value or "is-active" in value:
                return index
        return -1

    def expect_on_step(self, index: int) -> None:
        self.expect_visible(self.step(index))
