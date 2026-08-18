"""Browser fixtures: authenticated contexts, and evidence when things fail.

Two jobs here.

**Authentication is established once per run** and reused by every context, via
a storage-state file shared across xdist workers under a lock. The mechanism and
the reasons are in tests/utils/auth_state.py, which is where the interesting
part lives.

**Failures produce evidence, passes produce none.** A screenshot, a video and a
Playwright trace are attached to Allure when a test fails. Attaching them to
every test would bloat the report to the point where nobody opens any of them,
and would multiply the artifact storage a CI run keeps by the number of tests
that were never in doubt.
"""

from __future__ import annotations

from pathlib import Path

import allure
import pytest
from playwright.sync_api import Browser, BrowserContext, Page

from conftest import test_failed
from utils.auth_state import storage_state_file


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict, settings) -> dict:
    """Defaults every context inherits.

    A fixed viewport because a browser that sizes itself to the runner makes
    layout-dependent behaviour differ between a laptop and CI, and that
    difference always surfaces as a flaky test rather than as a resolution
    problem.
    """
    return {
        **browser_context_args,
        "base_url": settings.web_base_url.rstrip("/"),
        "viewport": {"width": 1280, "height": 800},
    }


@pytest.fixture(scope="session")
def signed_in_state(tmp_path_factory, worker_id: str, settings) -> Path:
    """Path to the shared storage-state file for the default identity.

    Session-scoped is an optimisation *within* a worker; the file lock is what
    makes it once-per-run across all of them.
    """
    return storage_state_file(tmp_path_factory, worker_id, settings)


def _new_page(
    browser: Browser,
    context_args: dict,
    artifacts: Path,
) -> tuple[BrowserContext, Page]:
    context = browser.new_context(
        **context_args,
        record_video_dir=str(artifacts / "video"),
    )
    # Screenshots and snapshots make the trace viewer's timeline scrubbable;
    # sources lets it show the test line that issued each action. All three are
    # what turn a trace from a log into something you can debug from.
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    return context, context.new_page()


def _finish(
    context: BrowserContext,
    page: Page,
    artifacts: Path,
    *,
    failed: bool,
    label: str,
) -> None:
    """Close the context, attaching evidence only when the test failed."""
    if failed:
        # Taken before anything is torn down, so it shows the state the
        # assertion actually saw.
        screenshot = artifacts / "failure.png"
        page.screenshot(path=str(screenshot), full_page=True)
        allure.attach.file(
            str(screenshot),
            name=f"screenshot — {label}",
            attachment_type=allure.attachment_type.PNG,
        )

    trace = artifacts / "trace.zip"
    # Stopping with a path writes the trace; stopping without one discards it,
    # which is the cheap path for the tests that passed.
    context.tracing.stop(path=str(trace) if failed else None)

    # The video is only finalised when the context closes, so it cannot be
    # attached before this point.
    context.close()

    if not failed:
        return

    allure.attach.file(
        str(trace),
        name=f"trace — {label} (open at trace.playwright.dev)",
        extension="zip",
    )

    video = page.video
    if video is not None:
        path = Path(video.path())
        if path.exists():
            allure.attach.file(
                str(path),
                name=f"video — {label}",
                attachment_type=allure.attachment_type.WEBM,
            )


@pytest.fixture
def page(browser, browser_context_args, signed_in_state, tmp_path, request):
    """An authenticated page: every test starts already signed in.

    This is the fixture nearly every browser test wants. The session comes from
    the shared storage-state file, so no test pays for a login it was not
    written to exercise.
    """
    context, page = _new_page(
        browser,
        {**browser_context_args, "storage_state": str(signed_in_state)},
        tmp_path,
    )
    yield page
    _finish(
        context, page, tmp_path,
        failed=test_failed(request.node),
        label=request.node.name,
    )


@pytest.fixture
def anonymous_page(browser, browser_context_args, tmp_path, request):
    """A page with no session at all.

    Deliberately does not take `signed_in_state`, so it never triggers the
    login that establishes it. This is what the login tests need — a browser
    that genuinely has not signed in.
    """
    context, page = _new_page(browser, dict(browser_context_args), tmp_path)
    yield page
    _finish(
        context, page, tmp_path,
        failed=test_failed(request.node),
        label=request.node.name,
    )
