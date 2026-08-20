"""Root fixtures: settings, database state, and one client per identity.

Scope is the whole design here. Anything expensive and immutable is built once
per session; anything a test could dirty is built per test. Between those two
sits the database reset, which is expensive, must happen exactly once, and must
happen before any test in any worker touches a row.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from filelock import FileLock

from clients import ApiClients
from config.settings import REPO_ROOT, TestSettings, get_settings
from utils.reporting import (
    DEFECTS,
    MODULE_FEATURES,
    area_for,
    defects_for,
    layer_for,
    sentence_for,
    severity_for,
    title_template,
)

logger = logging.getLogger("tests.setup")

# The application and this suite each read their own .env since the split, so
# TEST_API_KEY exists in two places and nothing keeps them in step. When they
# disagree the API answers 401, which reads like a broken test rather than a
# stale secret — so say what it actually is, and where both copies live.
CONFIGS_DRIFTED = """The configurations have drifted.

TEST_API_KEY in this repository does not match the one the application under
test was started with. They are separate files that nothing synchronises:

    this suite   {root}/.env
    the app      the engage-app checkout's .env, for a local server
                 the Render dashboard, for the deployed instance

Set both to the same value and run again."""


def _drift_message() -> str:
    return CONFIGS_DRIFTED.format(root=REPO_ROOT)

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


def _check_test_key(settings: TestSettings) -> None:
    """Refuse to start without the shared secret, and say where to put it.

    This runs before anything else touches the API. Without it the first failure
    is whatever test happened to run first, reported as that test's problem.

    Note what this deliberately does *not* do: probe the key by calling a
    guarded endpoint. Every one of them — reset, seed, truncate — writes. There
    is no read-only call that proves the right key works, so a probe would mean
    wiping a database in order to find out whether we were allowed to. When the
    session is going to reset anyway that check comes for free below; when it is
    not, the key stays unproven and this says so rather than implying otherwise.
    """
    if not settings.test_api_key:
        raise RuntimeError(
            "TEST_API_KEY is not set, so the suite cannot put the database into "
            "a known state.\n"
            f"Copy .env.example to {REPO_ROOT}/.env and set it to the value the "
            "application was started with."
        )

    if not settings.reset_database:
        logger.warning(
            "RESET_DATABASE=false: the database will not be reset, and "
            "TEST_API_KEY cannot be verified without writing to the target. A "
            "401 from a later guarded call means the configs have drifted."
        )


def _reset_database(settings: TestSettings) -> dict:
    """Put the database into the known seeded state, in one call."""
    # Logged because wiping a database is not a thing that should happen
    # invisibly — the report should say it did, and which worker did it.
    logger.info("Resetting database at %s", settings.api_base_url)
    response = httpx.post(
        f"{settings.api_base_url}/api/test/reset",
        headers={"X-Test-Key": settings.test_api_key},
        timeout=settings.request_timeout,
    )
    # This call is also the only proof that TEST_API_KEY is correct, so its
    # failures are worth telling apart: a rejected key is a configuration
    # problem, a disabled endpoint is a different configuration problem, and
    # anything else is the application being broken.
    if response.status_code == 401:
        raise RuntimeError(_drift_message())
    if response.status_code == 503:
        raise RuntimeError(
            "The application has no TEST_API_KEY configured, so its test "
            "endpoints are disabled and the database cannot be reset.\n"
            f"    POST /api/test/reset -> 503 {response.text[:200]}\n"
            "Set TEST_API_KEY for the application, not only for this suite."
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
    _check_test_key(settings)

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
        webhook_secret=settings.webhook_secret,
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




@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """Record each phase's result on the item, for fixtures to read at teardown.

    A fixture tearing down cannot otherwise tell whether its test passed. The
    browser fixtures need to know: a trace, a video and a screenshot are worth
    keeping for a failure and worth discarding for the two hundred passes, both
    for the size of the report and because an artefact attached to everything is
    an artefact nobody opens.
    """
    report = yield
    setattr(item, f"rep_{report.when}", report)
    return report


def test_failed(item: pytest.Item) -> bool:
    """Did the test body fail? Setup errors count too — a fixture that blew up
    mid-way is exactly when the trace is most useful."""
    return any(
        getattr(getattr(item, f"rep_{phase}", None), "failed", False)
        for phase in ("setup", "call")
    )


def _describe_for_the_report(item: pytest.Item) -> None:
    """Give one test the labels that make the report navigable.

    Applied centrally so all 138 tests gain structure without 138 decorators.
    Anything the test already declares for itself wins — a module that says
    `@allure.feature("Tenant isolation")` knows better than a lookup keyed on
    its filename.

    Labels are added as raw `allure_label` marks rather than through
    `allure.epic(...)`, because those helpers are decorators and return a
    function, not a mark. This is the same mechanism they use underneath.
    """
    module = item.module.__name__.rsplit(".", 1)[-1]
    name = item.originalname or item.name
    markers = {m.name for m in item.iter_markers()}
    callspec = getattr(item, "callspec", None)
    params = dict(callspec.params) if callspec else {}
    declared = {
        m.kwargs.get("label_type")
        for m in item.iter_markers(name="allure_label")
    }

    # Product area. Nothing declares an epic today, so this is purely additive
    # and is what the Behaviors tab groups by.
    if "epic" not in declared:
        item.add_marker(
            pytest.mark.allure_label(
                area_for(module, name, params), label_type="epic"
            )
        )

    # Finer grouping: the module's own feature, or the layer it belongs to.
    if "feature" not in declared:
        feature = MODULE_FEATURES.get(module) or layer_for(markers)
        item.add_marker(pytest.mark.allure_label(feature, label_type="feature"))

    if "story" not in declared:
        item.add_marker(
            pytest.mark.allure_label(sentence_for(name), label_type="story")
        )

    if "severity" not in declared:
        item.add_marker(
            pytest.mark.allure_label(
                severity_for(module, name), label_type="severity"
            )
        )

    # The layer, as a tag, so Graphs and the filter bar can slice by it.
    item.add_marker(pytest.mark.allure_label(layer_for(markers), label_type="tag"))

    # A failure in a test with a known defect is one click from its report.
    for defect in defects_for(module, name):
        item.add_marker(
            pytest.mark.allure_link(
                DEFECTS[defect], name=f"{defect} — known defect", link_type="issue"
            )
        )

    # Readable title. Set on the function because that is where allure-pytest
    # reads it from; the placeholders are what keep parametrised runs distinct.
    parameters = list(params)
    if not getattr(item.function, "__allure_display_name__", None):
        item.function.__allure_display_name__ = title_template(name, parameters)


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Describe every selected test for the report, then guard the selection.

    Both jobs belong in this hook: it runs after deselection, so it sees exactly
    the tests that will run.
    """
    for item in items:
        _describe_for_the_report(item)

    # The guard below fails the run when the selection is empty.
    #
    # `trylast` is load-bearing: `-m` deselection happens in pytest's own
    # implementation of this same hook, and without it this one runs first, sees
    # the full un-deselected list, and never fires — a guard that is itself
    # silently inactive, which is precisely the class of bug it exists to catch.
    #
    # pytest exits 5 for "no tests ran", and plenty of CI configurations treat
    # anything non-zero as red — but plenty of others check only for failures, and
    # a job that deselects everything then reports a green tick having verified
    # nothing. That is the worst possible outcome: silence that looks like proof.
    #
    # A marker typo is the usual cause, and `--strict-markers` cannot catch it,
    # because that guards markers applied to tests, not markers named in `-m`.
    #
    if items:
        return

    # One selector is legitimately empty: the destructive job runs `-m
    # destructive` on every build, and there are no destructive tests yet. That
    # is a known, deliberate emptiness, so it is opted out explicitly and per
    # job — which keeps the guard's meaning intact. An accidental empty
    # selection is still an error, because nothing sets this by accident.
    if os.environ.get("PYTEST_ALLOW_EMPTY_SELECTION") == "1":
        logger.warning(
            "No tests were selected, but PYTEST_ALLOW_EMPTY_SELECTION=1 is set, "
            "so this run is allowed to pass having verified nothing."
        )
        return

    selectors = []
    if getattr(config.option, "markexpr", ""):
        selectors.append(f"-m {config.option.markexpr!r}")
    if getattr(config.option, "keyword", ""):
        selectors.append(f"-k {config.option.keyword!r}")

    raise pytest.UsageError(
        "No tests were selected by "
        + (" and ".join(selectors) if selectors else "the arguments given")
        + ".\n"
        "Refusing to report success for a run that verified nothing. Check the "
        "expression against the markers registered in pyproject.toml.\n"
        "If this selection is legitimately empty, set "
        "PYTEST_ALLOW_EMPTY_SELECTION=1 for that run specifically."
    )


def _app_commit_sha(settings: TestSettings) -> str:
    """Which commit of the application these results describe.

    CI knows the answer exactly, because it checked the application out, and
    passes it in as APP_COMMIT_SHA. Locally it is read from a sibling checkout
    if there is one. Failing both, the report says "unknown": a stale or guessed
    SHA is worse than none, because it would be believed.
    """
    if settings.app_commit_sha:
        return settings.app_commit_sha

    repo = Path(settings.app_repo_path)
    if not repo.is_absolute():
        repo = (REPO_ROOT / repo).resolve()

    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"

    return completed.stdout.strip() or "unknown"


# How this suite actually fails, in the order a reader should think about it.
# Allure's default buckets are only "Product defects" and "Test defects", which
# put a stale secret, a dropped connection and a genuine bug in the same pile.
# Each entry below is a failure mode this suite has really produced.
#
# The regexes are full-match against the failure message, so each is wrapped in
# `(?s).*...*` — `(?s)` because these messages are multi-line.
ALLURE_CATEGORIES = [
    {
        # Checked before the generic buckets: this one has a known write-up.
        "name": "Known defect — DEF-001 (delete a referenced contact)",
        "matchedStatuses": ["failed", "broken"],
        "messageRegex": r"(?s).*(deliveries_contact_id_fkey|has deliveries and cannot be removed).*",
    },
    {
        "name": "Config drift — TEST_API_KEY mismatch",
        "matchedStatuses": ["failed", "broken"],
        "messageRegex": r"(?s).*(configurations have drifted|Missing or invalid X-Test-Key|TEST_API_KEY is not set).*",
    },
    {
        "name": "Transport failure — connection reset",
        "matchedStatuses": ["failed", "broken"],
        "messageRegex": r"(?s).*(TransportFailure|Connection reset by peer|ReadError|failed at the transport level).*",
    },
    {
        "name": "Application 5xx",
        "matchedStatuses": ["failed", "broken"],
        "messageRegex": r"(?s).*(actual status:\s+5\d\d|HTTP 5\d\d|Internal Server Error).*",
    },
    {
        "name": "Timeout waiting for a condition",
        "matchedStatuses": ["failed", "broken"],
        "messageRegex": r"(?s).*(WaitTimeout|condition was never met|Timeout \d+ms exceeded|TimeoutError).*",
    },
    # Catch-alls, last, so nothing lands outside a bucket.
    {"name": "Product defect", "matchedStatuses": ["failed"]},
    {"name": "Test or environment error", "matchedStatuses": ["broken"]},
]


def _write_categories(target: Path) -> None:
    """Publish the category definitions alongside the results.

    Written from the suite rather than kept as a file in the repository so it
    travels with every run — including a local `make report`, where nobody would
    remember to copy it in.
    """
    (target / "categories.json").write_text(
        json.dumps(ALLURE_CATEGORIES, indent=2), encoding="utf-8"
    )


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
    _write_categories(target)
    (target / "environment.properties").write_text(
        "\n".join(
            [
                f"API.Base.URL={settings.api_base_url}",
                f"Web.Base.URL={settings.web_base_url}",
                # The application is a separate repository now, so a report that
                # does not name the commit it tested cannot be reproduced. This
                # is the difference between "the suite failed in August" and
                # "the suite failed against engage-app 9e0645e".
                f"App.Commit={_app_commit_sha(settings)}",
                f"Database.Reset={str(settings.reset_database).lower()}",
                f"Python={platform.python_version()}",
                f"Platform={platform.platform()}",
                f"Pytest={pytest.__version__}",
                f"Executable={sys.executable}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
