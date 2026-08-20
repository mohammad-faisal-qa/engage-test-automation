"""Read-only database access, for the few facts HTTP cannot expose.

This is the one place in the suite that can talk to a database, and it is
deliberately the smallest thing that works. The risk it carries is not that
these three queries are wrong — it is that the door is now open, and the next
person under time pressure reaches for SQL because it is easier than making the
API tell them. TEST_STRATEGY.md §9 states the rules; this module enforces the
one that can be enforced mechanically.

**Read-only is enforced by Postgres, not by convention.** `read_only = True`
makes psycopg open every transaction with `BEGIN READ ONLY`, so an `INSERT`,
`UPDATE`, `DELETE` or `ALTER` is refused by the server: `cannot execute ... in a
read-only transaction`. A rule written in a docstring depends on everyone
reading it; a rule the server enforces does not. The statement check below
catches the same mistake earlier with a clearer message, but it is the
convenience and the server is the guarantee.

Read-only is a property of a *transaction*, not of a connection, so the
guarantee holds exactly as long as there is a transaction to have marked. Turn
autocommit on and there is not: `transaction_read_only` reverts to `off` and a
write succeeds. That is why the connection never leaves this module — `_read_only`
is private, `Database` exposes only reads, and no caller is ever handed something
whose autocommit it could flip.

**Two tempting alternatives are both wrong here, and one of them is dangerous.**

`options=-c default_transaction_read_only=on` at connect time is rejected outright
by a connection pooler — Neon's pooled endpoint calls it an unsupported startup
parameter — and every connection string in this project uses the pooled host.

`SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY` looks like the better fix,
because it covers autocommit too, and it appears to work. It must not be used.
The pooler multiplexes clients onto shared server connections, so the setting
outlives this session and is inherited by whoever is handed that connection next
— including the application under test. Setting it here put the *app* into
read-only sessions until the pool was cleared: `POST /api/test/reset` began
returning 500, and a brand-new connection opened by anyone reported
`transaction_read_only = on`. A test framework that can silently make the system
under test read-only is worse than the narrow gap it was closing.

**It has its own URL.** `TEST_DATABASE_URL`, never the application's
`DATABASE_URL`, so that pointing the suite at a database is a separate,
deliberate act from pointing the application at one. When it is unset the
db-marked tests skip and everything else runs, which means a fresh clone is
green with no database at hand.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Any, Iterator, Sequence

import psycopg

# Only statements that read. `WITH` is allowed because a CTE is still a SELECT,
# but a data-modifying CTE (`WITH ... AS (DELETE ...)`) would slip past this —
# which is why the server-side read-only setting is the real guarantee and this
# is only the earlier, friendlier error.
READ_ONLY_STATEMENT = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)


class WriteAttempted(RuntimeError):
    """A statement that was not a read reached the database layer."""


def _check(sql: str) -> None:
    if not READ_ONLY_STATEMENT.match(sql):
        raise WriteAttempted(
            f"The database layer accepts reads only, and this is not one:\n"
            f"  {sql.strip().splitlines()[0][:120]}\n"
            f"Nothing in this suite may write through SQL — not fixtures, not "
            f"cleanup. If a test needs data, it creates it through the API like "
            f"every other test does."
        )


@contextmanager
def _read_only(url: str) -> Iterator[psycopg.Connection]:
    """A connection the server itself will not let you write through.

    Private, and deliberately so. `read_only` is set before the caller can run
    anything, autocommit stays off precisely so that there *is* a transaction to
    mark, and the connection does not escape this module — which is what stops
    anyone turning autocommit back on and writing through it.
    """
    with psycopg.connect(url, autocommit=False, connect_timeout=30) as conn:
        conn.read_only = True
        yield conn


class Database:
    """A handful of read helpers over one URL. No session, no state, no writes."""

    def __init__(self, url: str) -> None:
        self.url = url

    def rows(self, sql: str, params: Sequence[Any] | None = None) -> list[tuple]:
        _check(sql)
        with _read_only(self.url) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        rows = self.rows(sql, params)
        return rows[0][0] if rows else None

    def count(self, sql: str, params: Sequence[Any] | None = None) -> int:
        value = self.scalar(sql, params)
        return int(value or 0)
