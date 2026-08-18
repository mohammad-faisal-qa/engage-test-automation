"""A paginated table with a filter toolbar.

Every list view in the application is the same shape — toolbar, table, pager —
differing only in the testid prefix and the columns. One component object serves
all of them, which is why `prefix` is a constructor argument rather than five
near-identical classes.
"""

from __future__ import annotations

import re

from playwright.sync_api import Locator

from pages.base_page import BasePage


class DataGrid(BasePage):
    """The grid on a list view, addressed by its testid prefix."""

    def __init__(self, page, settings, prefix: str) -> None:
        super().__init__(page, settings)
        self.prefix = prefix

    # --- rows --------------------------------------------------------------

    @property
    def body(self) -> Locator:
        return self.testid(f"{self.prefix}-tbody")

    @property
    def rows(self) -> Locator:
        """Data rows only.

        Scoped to the tbody rather than the table, because the header row is
        also a `tr` and counting it would make every expected count wrong by one.
        """
        return self.body.locator("tr")

    def row(self, record_id: int) -> Locator:
        return self.testid(f"{self.singular}-row-{record_id}")

    @property
    def singular(self) -> str:
        """`contacts` -> `contact`; row testids are singular in the markup."""
        return self.prefix[:-1] if self.prefix.endswith("s") else self.prefix

    def row_ids(self) -> list[int]:
        """The ids currently displayed, read from the row testids.

        Reading identity from the testid rather than the first cell means the
        column order can change without breaking every test that needed to know
        which records were on screen.
        """
        ids = []
        for value in self.rows.evaluate_all(
            "rows => rows.map(r => r.getAttribute('data-testid'))"
        ):
            match = re.search(r"-row-(\d+)$", value or "")
            if match:
                ids.append(int(match.group(1)))
        return ids

    # --- state -------------------------------------------------------------

    @property
    def page_info(self) -> Locator:
        return self.testid(f"{self.prefix}-page-info")

    @property
    def empty_message(self) -> Locator:
        return self.testid(f"{self.prefix}-empty")

    @property
    def error_message(self) -> Locator:
        return self.testid(f"{self.prefix}-error")

    def total(self) -> int:
        """The record count the server reported, taken from the data attribute
        rather than parsed out of the sentence — the wording is presentation and
        may change; the number is the contract."""
        value = self.page_info.get_attribute("data-total")
        return int(value) if value is not None else -1

    # --- paging ------------------------------------------------------------

    @property
    def next_button(self) -> Locator:
        return self.testid(f"{self.prefix}-next")

    @property
    def previous_button(self) -> Locator:
        return self.testid(f"{self.prefix}-prev")

    def next_page(self) -> None:
        self.next_button.click()

    def previous_page(self) -> None:
        self.previous_button.click()

    def expect_loaded(self) -> None:
        """Wait until the grid has finished its first request.

        The body starts as a single "Loading…" row, so waiting for *any* row is
        not enough — a test could assert against the placeholder. Waiting for the
        pager to carry a total is the signal that a response actually landed.

        Only good for a *first* load. `data-total` is sticky, so after a page
        change it is already set and this returns immediately, before the new
        rows exist. Use `expect_page` when moving between pages — the bug that
        wait hides is a test reading the previous page and passing anyway.
        """
        self.expect_visible(self.page_info)
        self.page.wait_for_function(
            "prefix => {"
            "  const el = document.querySelector(`[data-testid='${prefix}-page-info']`);"
            "  return el && el.dataset.total !== undefined;"
            "}",
            arg=self.prefix,
            timeout=self._ms(None),
        )

    def expect_page(self, number: int) -> None:
        """Wait until the grid is showing a specific page.

        Distinguishes one page from another, which `expect_loaded` cannot. The
        application writes the pager text and the rows in one synchronous block,
        so once the text says "Page 2" the rows beneath it are page 2's.
        """
        self.expect_contains_text(self.page_info, f"Page {number} of")

    def expect_row_count(self, count: int) -> None:
        """Auto-waiting count assertion — unlike reading `row_ids()`, which
        snapshots whatever is in the DOM at that instant."""
        self.expect_count(self.rows, count)
