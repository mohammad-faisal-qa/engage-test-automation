"""Root fixtures: settings, database state, and one client per identity.

Scope is the whole design here. Anything expensive and immutable is built once
per session; anything a test could dirty is built per test. Between those two
sits the database reset, which is expensive, must happen exactly once, and must
happen before any test in any worker touches a row.
"""

from __future__ import annotations

import logging
import platform
import sys
from pathlib import Path

import httpx
import pytest
from filelock import FileLock

from clients import ApiClients
from config.settings import TestSettings, get_settings

logger = logging.getLogger("tests.setup")

# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------


@pytest.fixture(scope="session")
def settings() -> TestSettings:
    """Parsed once per session; `.env` does not change mid-run."""
    return get_settings()


# --------------------------------------------------------------------------
# Environment preconditions and database state
# --------------------------------------------------------------------------


def _check_api_is_up(settings: TestSettings) -> None:
    """Fail with an instruction rather than a connection error.

    A stack trace from httpx tells you the socket was refused. It does not tell
    you to start the server, and that is the only thing the reader needs.
    """
    health_url = f"{settings.api_base_url}/api/health"
    try:
        response = httpx.get(health_url, timeout=settings.request_timeout)
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Cannot reach the Engage API at {settings.api_base_url} ({exc}).\n"
            f"Start it from the engage-app repository with:\n"
            f"    cd <engage-app>/api && .venv/bin/uvicorn app.main:app --reload\n"
            f"or point the suite elsewhere with API_BASE_URL=<url>."
        ) from exc

    body = response.json()
    if response.status_code != 200 or body.get("status") != "ok":
        raise RuntimeError(
            f"The API at {settings.api_base_url} is reachable but not healthy.\n"
            f"    GET /api/health -> {response.status_code} {body}\n"
            f"A 'degraded' status with an unreachable database usually means "
            f"DATABASE_URL is wrong or the database is asleep."
        )


def _reset_database(settings: TestSettings) -> dict:
    """Put the database into the known seeded state, in one call."""
    if not settings.test_api_key:
        raise RuntimeError(
            "TEST_API_KEY is not set, so the suite cannot reset the database.\n"
            "Add it to the repo-root .env (the value the API was started with)."
        )

    # Logged because wiping a database is not a thing that should happen
    # invisibly — the report should say it did, and which worker did it.
    logger.info("Resetting database at %s", settings.api_base_url)
    response = httpx.post(
        f"{settings.api_base_url}/api/test/reset",
        headers={"X-Test-Key": settings.test_api_key},
        timeout=settings.request_timeout,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Database reset failed: POST /api/test/reset -> "
            f"{response.status_code} {response.text[:300]}"
        )
    counts = response.json().get("counts", {})
    logger.info("Database reset complete: %s", counts)
    return counts


@pytest.fixture(scope="session", autouse=True)
def database_state(settings: TestSettings, tmp_path_factory, worker_id: str) -> None:
    """Reset the database exactly once per session, including under xdist.

    Autouse, so no test can accidentally run against unknown state by forgetting
    to ask for it. Session-scoped, because resetting per test would be both slow
    and pointless — tests create their own uniquely-named data instead.

    The two branches are not symmetric, and the reason is a real trap:

      serial   `tmp_path_factory.getbasetemp().parent` is the *pytest root*,
               which is reused by every run on the machine. A marker file
               written there would still exist tomorrow, and the reset would be
               silently skipped from the second run onwards. With no other
               process to coordinate with, the honest answer is to just do it.

      xdist    `getbasetemp()` is `.../pytest-N/popen-gwX`, so `.parent` is
               `.../pytest-N` — shared by this run's workers and created fresh
               for each run. That is the correct place for the lock and marker.

    The lock is what makes the check-then-act safe: without it, four workers can
    all observe "no marker" at once and all reset, with three of them wiping
    rows the other's tests are mid-way through reading.
    """
    _check_api_is_up(settings)

    if not settings.reset_database:
        return

    if worker_id == "master":
        _reset_database(settings)
        return

    shared_dir: Path = tmp_path_factory.getbasetemp().parent
    marker = shared_dir / "database-reset.done"

    with FileLock(str(shared_dir / "database-reset.lock")):
        if not marker.exists():
            _reset_database(settings)
            # Written only after the reset returns, so a worker that acquires
            # the lock next waits for a finished reset, not a started one.
            marker.write_text("done", encoding="utf-8")


# --------------------------------------------------------------------------
# API clients
# --------------------------------------------------------------------------


@pytest.fixture(scope="session")
def api(settings: TestSettings, database_state: None) -> ApiClients:
    """Every service client, for every role and tenant.

    Session-scoped because a token is valid for the whole run and logging in
    costs a bcrypt verification each time. Depends on `database_state` so no
    token is ever minted against a database that is about to be wiped.

    Usage reads as the identity it is testing:
        api.contacts()                 admin of acme, the common case
        api.contacts(role="viewer")    viewer of acme
        api.contacts(tenant="globex")  admin of globex
    """
    clients = ApiClients(
        settings.api_base_url,
        timeout=settings.request_timeout,
        password=settings.seed_password,
        email_for=settings.user_email,
    )
    yield clients
    clients.close()


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Give each xdist worker its own log file.

    Without this, `--log-file` hands the same path to every worker and they
    overwrite one another: the result is a single file of interleaved, truncated
    lines that is actively misleading, because entries are missing rather than
    obviously wrong. Suffixing with the worker id costs nothing and makes the
    logs usable as evidence.
    """
    log_file = getattr(config.option, "log_file", None)
    worker_id = getattr(config, "workerinput", {}).get("workerid")
    if log_file and worker_id:
        path = Path(log_file)
        config.option.log_file = str(path.with_name(f"{path.stem}-{worker_id}{path.suffix}"))




def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Record what was tested, so a report six months old still means something.

    Written only from the controller process: under xdist every worker would
    otherwise race to write the same file.
    """
    if hasattr(session.config, "workerinput"):
        return

    results_dir = getattr(session.config.option, "allure_report_dir", None)
    if not results_dir:
        return

    settings = get_settings()
    target = Path(results_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "environment.properties").write_text(
        "\n".join(
            [
                f"API.Base.URL={settings.api_base_url}",
                f"Web.Base.URL={settings.web_base_url}",
                f"Python={platform.python_version()}",
                f"Platform={platform.platform()}",
                f"Pytest={pytest.__version__}",
                f"Executable={sys.executable}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
