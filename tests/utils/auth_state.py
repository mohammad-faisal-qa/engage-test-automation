"""Browser authentication, established once and shared by every worker.

Logging in through the UI costs a page load, a form submit, a bcrypt
verification and a redirect. Doing that before each of twenty-odd browser tests
would make the login screen the most-tested part of the application by an order
of magnitude, and none of those logins would be testing anything. Playwright's
answer is `storage_state`: capture the browser state of a logged-in session once,
and start every context from it.

The interesting problem is *once* — under `-n 4` there are four processes.

Why an in-memory cache does not work
------------------------------------
The obvious implementation is a module-level dict, or a session-scoped fixture,
holding the state after the first login. Both work perfectly in serial and do
nothing at all under xdist, for a reason that is easy to miss: **xdist workers
are separate operating-system processes, not threads.** `pytest -n 4` forks four
interpreters, each with its own memory, its own import of this module, and its
own session-scoped fixture cache. "Session scope" means *this worker's* session.

So a session-scoped login fixture under `-n 4` logs in four times, not once, and
scaling to `-n 8` logs in eight times. Nothing fails — it is just quietly linear
in worker count, which is the opposite of why anyone reaches for xdist.

Anything shared between processes has to live outside them, and the only thing
they reliably share is the filesystem.

What the lock protects
----------------------
Writing the state to a file gets it across the process boundary but introduces a
race, because the sequence is check-then-act:

    if not state_file.exists():      # four workers can all be here at once
        log_in_and_write(state_file) # ...and all four then write

Without coordination, four workers observe "no file", four log in, and four write
the same path concurrently — so a fifth reader can see a half-written file and
fail to parse it. The failure is rare, load-dependent, and looks like flakiness
rather than a bug, which is the worst kind.

The lock makes check-then-act atomic: exactly one worker finds the file missing
and creates it, and the others block until it is *finished*, not merely started.
The file is written to a temporary name and renamed into place, so even a reader
that somehow bypassed the lock sees either no file or a complete one — `rename`
is atomic within a filesystem.

Where the lock lives matters too, and the directory is not the obvious one. See
`shared_directory` below.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
from filelock import FileLock

logger = logging.getLogger("tests.setup")

# The key the frontend stores its JWT under; see web/src/api.js. Naming it here
# is a real coupling to the application, and the honest place for it: the whole
# point of storage_state is to reproduce what the browser would have held.
TOKEN_STORAGE_KEY = "engage_token"


def shared_directory(tmp_path_factory, worker_id: str) -> Path:
    """The directory every worker in *this run* can see, and no other run can.

    The two branches are not symmetric, and the asymmetry is the trap:

      xdist   `getbasetemp()` is `.../pytest-N/popen-gwX`, so `.parent` is
              `.../pytest-N` — created fresh for this run and shared by its
              workers. Exactly right.

      serial  `getbasetemp()` is already `.../pytest-N`. Taking `.parent` here
              would give the *pytest root*, which is reused by every run on the
              machine — so the state file would still be there tomorrow, holding
              a token that expired overnight, and every run after the first
              would start from it.

    So serial uses the base temp directory itself, and only xdist goes up one.
    """
    base = tmp_path_factory.getbasetemp()
    return base if worker_id == "master" else base.parent


def storage_state_file(
    tmp_path_factory,
    worker_id: str,
    settings,
    *,
    role: str = "admin",
    tenant: str = "acme",
) -> Path:
    """Path to a storage-state JSON for one identity, creating it if needed.

    Safe to call from every worker concurrently: at most one login happens.
    """
    shared = shared_directory(tmp_path_factory, worker_id)
    state_file = shared / f"storage-state-{role}-{tenant}.json"
    lock_file = shared / f"storage-state-{role}-{tenant}.lock"

    with FileLock(str(lock_file)):
        if not state_file.exists():
            _write_storage_state(state_file, settings, role=role, tenant=tenant)

    return state_file


def _write_storage_state(destination: Path, settings, *, role: str, tenant: str) -> None:
    """Mint a session and write it in Playwright's storage-state format.

    The token is obtained from the API rather than by driving the login form.
    That is deliberate: this runs as *setup* for every browser test, and setup
    that goes through the UI makes an unrelated failure — a broken login screen —
    surface as twenty errors in twenty tests that were about something else.
    Login through the browser is worth testing exactly once, and it is, in
    test_login.py.

    Only the token is needed. The frontend re-fetches the user from /auth/me on
    load (see `auth.restore` in web/src/store.js), so a session is fully
    reconstituted from this one value.
    """
    # Logged for the same reason the database reset is: this should happen once
    # per run, and the only way to know it did is to be able to count it.
    logger.info("Establishing a browser session for %s@%s", role, tenant)
    response = httpx.post(
        f"{settings.api_base_url}/api/auth/login",
        json={
            "email": settings.user_email(role, tenant),
            "password": settings.seed_password,
        },
        timeout=settings.request_timeout,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Could not establish a browser session for {role}@{tenant}: "
            f"POST /api/auth/login -> {response.status_code} {response.text[:200]}"
        )

    state = {
        "cookies": [],
        "origins": [
            {
                "origin": settings.web_base_url.rstrip("/"),
                "localStorage": [
                    {
                        "name": TOKEN_STORAGE_KEY,
                        "value": response.json()["access_token"],
                    }
                ],
            }
        ],
    }

    # Written under a temporary name and renamed into place. Within one
    # filesystem rename is atomic, so no reader can ever observe a partial file
    # — belt and braces alongside the lock.
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(destination)
