"""Deletion confirmations.

FRAMEWORK_BUILD lists a `modal` component here, written before the application
existed. The application has no modal: every destructive action in all five
views calls `window.confirm`, which is a *native browser dialog*, not markup.
There is nothing in the DOM to locate, so a page object built around selectors
would have had nothing to select.

Playwright suppresses native dialogs by default — an unhandled `confirm` is
auto-dismissed, which means an unprepared test silently takes the "Cancel" path
and then fails somewhere else entirely, asserting that a record it never
confirmed deleting is still present. This component makes the choice explicit.
"""

from __future__ import annotations

from contextlib import contextmanager

from playwright.sync_api import Page


class ConfirmDialog:
    """Decide, in advance, how the next native dialog is answered."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.last_message: str | None = None

    @contextmanager
    def accept(self):
        """Confirm the next dialog, recording what it asked.

        The message is captured so a test can assert the user was told *which*
        record they were deleting — a confirmation that names nothing is a
        confirmation nobody reads.
        """
        yield from self._answer(accept=True)

    @contextmanager
    def dismiss(self):
        """Cancel the next dialog — the path that must leave data untouched."""
        yield from self._answer(accept=False)

    def _answer(self, *, accept: bool):
        def handle(dialog):
            self.last_message = dialog.message
            dialog.accept() if accept else dialog.dismiss()

        self.page.on("dialog", handle)
        try:
            yield self
        finally:
            self.page.remove_listener("dialog", handle)
