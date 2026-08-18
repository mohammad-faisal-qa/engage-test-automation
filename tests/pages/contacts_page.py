"""The contacts grid: paging, search, filters and the inline editor."""

from __future__ import annotations

from urllib.parse import urlencode

from playwright.sync_api import Locator

from pages.base_page import BasePage
from pages.components.confirm_dialog import ConfirmDialog
from pages.components.data_grid import DataGrid
from pages.components.nav import Nav


class ContactsPage(BasePage):
    """Wraps #/contacts.

    Grid state is entirely in the URL, so `open_with` builds a deep link rather
    than driving the toolbar. Reaching page 3 of a filtered search by clicking
    is four interactions that can each fail for their own reasons; the link is
    one navigation, and it is what a shared URL would do anyway.
    """

    def __init__(self, page, settings) -> None:
        super().__init__(page, settings)
        self.grid = DataGrid(page, settings, "contacts")
        self.nav = Nav(page, settings)
        self.dialog = ConfirmDialog(page)

    # --- navigation --------------------------------------------------------

    def open_with(self, **state) -> None:
        """Deep-link to a grid state: page, size, q, country, plan."""
        params = {key: value for key, value in state.items() if value not in (None, "")}
        route = "/contacts" + (f"?{urlencode(params)}" if params else "")
        self.open(route)
        self.expect_visible("contacts-view")

    def open_grid(self) -> None:
        self.open_with()
        self.grid.expect_loaded()

    # --- toolbar -----------------------------------------------------------

    @property
    def search_box(self) -> Locator:
        # Labelled for assistive technology, so located the way a person finds it.
        return self.label("Search contacts")

    def search_for(self, term: str) -> None:
        """Type and press Enter — the application filters on Enter, not on every
        keystroke, so this is the moment a request is actually issued."""
        self.search_box.fill(term)
        self.search_box.press("Enter")

    def filter_country(self, code: str) -> None:
        self.label("Filter by country").select_option(code)

    def filter_plan(self, plan: str) -> None:
        self.label("Filter by plan").select_option(plan)

    def set_page_size(self, size: int) -> None:
        self.label("Rows per page").select_option(str(size))

    def clear_filters(self) -> None:
        self.role("button", name="Clear").click()

    # --- rows and actions --------------------------------------------------

    def edit_button(self, contact_id: int) -> Locator:
        return self.testid(f"contact-edit-{contact_id}")

    def delete_button(self, contact_id: int) -> Locator:
        return self.testid(f"contact-delete-{contact_id}")

    @property
    def new_button(self) -> Locator:
        return self.testid("contact-new")

    def delete(self, contact_id: int, *, confirm: bool = True) -> None:
        answer = self.dialog.accept() if confirm else self.dialog.dismiss()
        with answer:
            self.delete_button(contact_id).click()
