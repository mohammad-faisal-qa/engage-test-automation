"""Refusing to destroy the thing we are supposed to be protecting.

`database_state` resets the database before the suite runs, and the reset is
total: every table wiped, the seed re-inserted. That is correct against a
throwaway database and catastrophic against the live demo, and until this
module existed nothing distinguished the two.

The realistic accident is not "someone points the suite at the production URL" —
that is visible in `API_BASE_URL` and someone would notice. It is that the
*local* application, reached at `127.0.0.1`, is itself configured against the
production database. From the suite's side that is indistinguishable from a
normal local run: the URL is localhost, the health check is green, and the reset
wipes production. It has a name now — DEF-005 — and this is the guard.

Two signals, because either one alone leaves a hole:

  the database endpoint   catches a local app pointed at production, which the
                          URL cannot reveal. This is the important one.
  the API hostname        catches the suite pointed straight at the deployed
                          instance, which the endpoint cannot reveal when the
                          deployed app is too old to report it.

Kept as a pure function on purpose: a guard nobody can test is a guard nobody
should trust, and testing this one against a real production database is not an
option.
"""

from __future__ import annotations

from urllib.parse import urlparse


def looks_like_production(
    *,
    api_base_url: str,
    database_endpoint: str | None,
    production_endpoint_id: str,
    production_api_hosts: tuple[str, ...],
) -> str | None:
    """Describe why this target looks like production, or `None` if it does not.

    Returns a sentence rather than a bool so the caller can say *what* it
    detected. "Refusing to reset" without naming the evidence is the kind of
    message people work around.
    """
    if database_endpoint and production_endpoint_id:
        # Compare on the endpoint label, ignoring a `-pooler` suffix: Neon's
        # pooled and direct hosts are the same database and only one of them
        # would otherwise match.
        seen = database_endpoint.removesuffix("-pooler")
        expected = production_endpoint_id.removesuffix("-pooler")
        if seen == expected:
            return (
                f"the application is connected to database endpoint {seen!r}, "
                f"which is the production endpoint"
            )

    host = (urlparse(api_base_url).hostname or "").lower()
    if host and host in {h.lower() for h in production_api_hosts if h}:
        return f"the API under test is {host!r}, which is the deployed instance"

    return None


def refusal_message(reason: str, override_variable: str) -> str:
    """What the suite prints instead of destroying the demo."""
    return (
        f"Refusing to reset the database: {reason}.\n"
        f"\n"
        f"A reset wipes every table and re-inserts the seed. Against the live "
        f"demo that discards whatever anyone has done with it, and there is no "
        f"undo.\n"
        f"\n"
        f"If the target is wrong, fix it — the database the local application "
        f"opens is set by DATABASE_URL in the engage-app checkout's .env, and "
        f"the endpoint it resolves to is reported by GET /api/health as "
        f"`database_endpoint`.\n"
        f"\n"
        f"If you genuinely mean to reset this target, set {override_variable}=true. "
        f"Do that deliberately and never in a script that runs unattended."
    )
