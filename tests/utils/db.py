"""Read-only database access, for the few facts HTTP cannot expose.

This is the one place in the suite that can talk to a database, and it is
deliberately the smallest thing that works. The risk it carries is not that
these three queries are wrong — it is that the door is now open, and the next
person under time pressure reaches for SQL because it is easier than making the
API tell them. TEST_STRATEGY.md §9 states the rules; this module enforces the
one that can be enforced mechanically.

**Read-only is enforced by Postgres, not by convention.** Every transaction is
opened with `BEGIN READ ONLY`, so an `INSERT`, `UPDATE`, `DELETE` or `ALTER` is
refused by the server with `cannot execute ... in a read-only transaction`. A
rule written in a docstring depends on everyone reading it; a rule the server
enforces does not. A statement check on the way in catches the same mistake
earlier, with a clearer message.

The obvious implementation — passing `options=-c default_transaction_read_only=on`
at connect time — does not survive a connection pooler: Neon's pooled endpoint
rejects it outright as an unsupported startup parameter, and every connection
string in this project uses the pooled host. `BEGIN READ ONLY` is an ordinary
statement inside the session, so it works through a pooler and gives the same
guarantee.

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
def read_only(url: str) -> Iterator[psycopg.Connection]:
    """A connection the server itself will not let you write through.

    `read_only` makes psycopg open each transaction with `BEGIN READ ONLY`;
    autocommit stays off precisely so that there *is* a transaction to mark.
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
        with read_only(self.url) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        rows = self.rows(sql, params)
        return rows[0][0] if rows else None

    def count(self, sql: str, params: Sequence[Any] | None = None) -> int:
        value = self.scalar(sql, params)
        return int(value or 0)
