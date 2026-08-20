"""The guard that stops the suite resetting the live demo.

A guard is only worth having if it has been seen to refuse. These tests are the
only way to watch this one refuse without an actual production database to point
it at, which is exactly why it is a pure function.

The case that matters most is the third: localhost, healthy, and production
underneath. That is DEF-005, and it is invisible to every other signal the suite
has — the URL says `127.0.0.1`, the health check says `ok`, and the reset wipes
the demo.
"""

import pytest

from utils.safety import looks_like_production, refusal_message

pytestmark = [pytest.mark.unit, pytest.mark.readonly]

PRODUCTION_ENDPOINT = "ep-round-snow-axyc70lw"
PRODUCTION_HOSTS = ("engage-api-b6yg.onrender.com",)
TEST_ENDPOINT = "ep-falling-firefly-axrf9s08"


def check(api_base_url: str, database_endpoint: str | None) -> str | None:
    return looks_like_production(
        api_base_url=api_base_url,
        database_endpoint=database_endpoint,
        production_endpoint_id=PRODUCTION_ENDPOINT,
        production_api_hosts=PRODUCTION_HOSTS,
    )


def test_an_ordinary_local_run_is_allowed():
    """The common case must stay silent, or the guard becomes noise people mute."""
    assert check("http://127.0.0.1:8000", TEST_ENDPOINT) is None


def test_a_local_api_pointed_at_production_is_refused():
    """DEF-005 itself.

    Everything a reader would check looks fine — the URL is localhost — and the
    database underneath is the live one. Only the endpoint gives it away.
    """
    reason = check("http://127.0.0.1:8000", PRODUCTION_ENDPOINT)
    assert reason is not None, (
        "a local API connected to the production database was allowed to be "
        "reset — this is the exact accident DEF-005 describes"
    )
    assert PRODUCTION_ENDPOINT in reason


def test_the_deployed_api_is_refused():
    reason = check("https://engage-api-b6yg.onrender.com", None)
    assert reason is not None
    assert "engage-api-b6yg.onrender.com" in reason


@pytest.mark.parametrize(
    "endpoint",
    ["ep-round-snow-axyc70lw", "ep-round-snow-axyc70lw-pooler"],
    ids=["direct", "pooled"],
)
def test_the_pooled_and_direct_hosts_are_both_recognised(endpoint):
    """Neon exposes one database under two hostnames. Matching only the exact
    string would let the pooled form through, which is the form every connection
    string in this project actually uses.
    """
    assert check("http://127.0.0.1:8000", endpoint) is not None


def test_an_older_application_that_cannot_report_its_endpoint_still_falls_back():
    """`database_endpoint` is None when the app predates that field. The URL
    check has to keep working on its own, or deploying the guard before the app
    would leave a window with no protection at all.
    """
    assert check("https://engage-api-b6yg.onrender.com", None) is not None
    assert check("http://127.0.0.1:8000", None) is None


def test_the_refusal_says_what_it_found_and_how_to_proceed():
    """A refusal nobody can act on gets worked around rather than read."""
    message = refusal_message(check("http://127.0.0.1:8000", PRODUCTION_ENDPOINT),
                              "ALLOW_PRODUCTION_RESET")
    assert PRODUCTION_ENDPOINT in message
    assert "ALLOW_PRODUCTION_RESET" in message
    assert "DATABASE_URL" in message
    assert "no undo" in message
