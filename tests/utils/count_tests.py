"""Generate the README's test counts from the tests themselves, and check them.

A README that states how many tests there are is stating something that changes
every time somebody adds one. Written by hand it is wrong within a week, and a
wrong number in the first paragraph is worse than no number: it is the one claim
a reader can check in ten seconds.

So the numbers are generated from a real pytest collection — the same collection
`make all` runs — and CI fails when the file disagrees with the code. That makes
the README a derived artefact for the parts that can drift, and prose everywhere
else.

Two modes:

    python tests/utils/count_tests.py --write    rewrite the generated regions
    python tests/utils/count_tests.py --check    exit 1 if they are out of date

Collection touches no network and needs no running application, so `--check` is
a job with no service container and nothing to boot.

Two kinds of generated region, both invisible in rendered Markdown:

    <!--n:total-->151<!--/n-->        a single number, inline in a sentence
    <!--table:groups-->…<!--/table--> a whole table
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"

# The groups a reader cares about, in the order they should be read: what the
# suite mostly is, then what it adds. `layer_for()` in reporting.py is the same
# function the Allure report labels tests with, so the report and the README
# cannot disagree about what a test is.
GROUPS: list[tuple[str, str, str, str]] = [
    # key,       layer,      selected by,          where
    ("api", "API", "`-m api`, minus contract", "`tests/api_tests/`"),
    ("contract", "Contract", "`-m contract`", "`tests/api_tests/test_contract_openapi.py`"),
    ("ui", "Browser", "`-m ui`", "`tests/ui_tests/`"),
    ("bdd", "Journey", "`-m e2e`", "`tests/features/` + `tests/steps/`"),
    ("db", "Database", "`-m db`", "`tests/db_tests/`"),
    ("guard", "Unit", "`-m unit`", "`tests/test_reset_guard.py`"),
]

GROUP_LABELS = {
    "api": "Functional API",
    "contract": "Contract",
    "ui": "Browser (UI)",
    "bdd": "BDD journeys",
    "db": "Database",
    "guard": "Guard",
}

GROUP_ANSWERS = {
    "api": "Does the application behave correctly?",
    "contract": "Does it still promise what its clients depend on?",
    "ui": "Does the interface work, and fail, correctly?",
    "bdd": "Do the business outcomes hold end to end?",
    "db": "Is the stored data right where no response could show it?",
    "guard": "Does the suite refuse to destroy what it protects?",
}


class _Collector:
    """Captures collected items without running any of them."""

    def __init__(self) -> None:
        self.items: list = []

    def pytest_collection_modifyitems(self, items) -> None:
        self.items = list(items)


def collect() -> dict[str, int]:
    """Every number the README states, from one real collection."""
    sys.path.insert(0, str(REPO_ROOT / "tests"))
    from utils.reporting import layer_for  # noqa: E402  (needs the path above)

    # Collection prints every test id, which would bury the one line that
    # matters. Held back and replayed only if something actually went wrong.
    collector = _Collector()
    chatter = io.StringIO()
    with contextlib.redirect_stdout(chatter):
        code = pytest.main(
            ["--collect-only", "-q", "-p", "no:cacheprovider", str(REPO_ROOT / "tests")],
            plugins=[collector],
        )
    if code != 0 or not collector.items:
        print(chatter.getvalue(), file=sys.stderr)
        raise SystemExit(f"collection failed (pytest exit {code}) — counts not written")

    by_layer: dict[str, int] = {}
    by_marker: dict[str, int] = {}
    for item in collector.items:
        markers = {m.name for m in item.iter_markers()}
        by_layer[layer_for(markers)] = by_layer.get(layer_for(markers), 0) + 1
        for name in markers:
            by_marker[name] = by_marker.get(name, 0) + 1

    numbers = {"total": len(collector.items)}
    for key, layer, _, _ in GROUPS:
        numbers[key] = by_layer.get(layer, 0)
    for marker in ("smoke", "readonly", "destructive"):
        numbers[marker] = by_marker.get(marker, 0)

    # What a fresh clone actually sees: no TEST_DATABASE_URL, so the database
    # tests skip. Derived rather than written down, for the same reason as the
    # rest of this file.
    numbers["without_db"] = numbers["total"] - numbers["db"]

    # Every test must land in exactly one group, or the table lies by omission.
    grouped = sum(numbers[key] for key, _, _, _ in GROUPS)
    if grouped != numbers["total"]:
        raise SystemExit(
            f"{numbers['total'] - grouped} test(s) fall into no group. Add a "
            f"layer for the new marker in utils/reporting.py, or the README "
            f"table will silently omit them.\n"
            f"  layers seen: {sorted(by_layer)}"
        )
    return numbers


def groups_table(numbers: dict[str, int]) -> str:
    rows = [
        "| Group | Count | What it answers | Selected by | Where |",
        "|---|---:|---|---|---|",
    ]
    for key, _, selector, where in GROUPS:
        rows.append(
            f"| {GROUP_LABELS[key]} | {numbers[key]} | {GROUP_ANSWERS[key]} "
            f"| {selector} | {where} |"
        )
    rows.append(f"| **Total** | **{numbers['total']}** | | `make all` | |")
    return "\n".join(rows)


TOKEN = re.compile(r"(<!--n:(\w+)-->)(.*?)(<!--/n-->)", re.DOTALL)
TABLE = re.compile(r"(<!--table:groups-->)(.*?)(<!--/table-->)", re.DOTALL)


def render(text: str, numbers: dict[str, int]) -> str:
    def one_number(match: re.Match) -> str:
        name = match.group(2)
        if name not in numbers:
            raise SystemExit(
                f"README asks for <!--n:{name}--> and nothing computes it. "
                f"Known: {', '.join(sorted(numbers))}"
            )
        return f"{match.group(1)}{numbers[name]}{match.group(4)}"

    text = TOKEN.sub(one_number, text)
    return TABLE.sub(lambda m: f"{m.group(1)}\n{groups_table(numbers)}\n{m.group(3)}", text)


def missing_regions(text: str) -> list[str]:
    """Which generated regions the README has lost.

    Without this the check passes vacuously: delete the markers and there is
    nothing left to disagree with the code, so a README full of hand-written
    numbers goes green. A guard that can be silenced by deleting it is not a
    guard, and this is the way it would happen — not maliciously, but in a
    rewrite by someone who did not know the comments meant anything.
    """
    missing = []
    if not TABLE.search(text):
        missing.append("the group table — `<!--table:groups-->` … `<!--/table-->`")
    if not any(m.group(2) == "total" for m in TOKEN.finditer(text)):
        missing.append("the total — `<!--n:total-->151<!--/n-->`")
    return missing


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--check"
    current = README.read_text(encoding="utf-8")

    gone = missing_regions(current)
    if gone:
        print(
            "README counts: BROKEN — the generated regions are not in the file.\n"
            + "".join(f"  missing: {m}\n" for m in gone)
            + "  These markers are invisible in rendered Markdown and are what keeps\n"
              "  the README honest. Restore them, then run `make counts`."
        )
        return 1

    numbers = collect()
    updated = render(current, numbers)

    if mode == "--write":
        if updated == current:
            print(f"README counts already current — {numbers['total']} tests.")
            return 0
        README.write_text(updated, encoding="utf-8")
        print(f"README counts rewritten — {numbers['total']} tests.")
        return 0

    if updated == current:
        print(f"README counts: OK — {numbers['total']} tests, and the README says so.")
        return 0

    stale = [
        f"  {name}: README says {found or '(empty)'}, collection says {numbers[name]}"
        for _, name, found, _ in (m.groups() for m in TOKEN.finditer(current))
        if name in numbers and found.strip() != str(numbers[name])
    ]
    print(
        "README counts: STALE — the README disagrees with the tests it describes.\n"
        + ("\n".join(stale) + "\n" if stale else "  the group table is out of date\n")
        + "  Run `make counts` and commit the result."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
