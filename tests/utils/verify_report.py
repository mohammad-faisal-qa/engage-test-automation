"""Check that a generated report contains everything that was put into it.

Twice now a report has been described that did not contain the whole run. The
first time a browser job finished after the report was generated; the second
time the report was simply never regenerated after the last run, so it described
145 tests while the suite had just reported 146.

Both were caught by reading numbers side by side and noticing they disagreed,
which is not a control — it is luck. Printing the input count helped and was not
enough, because a number on its own still has to be compared by a human who has
already decided the run went fine.

So this compares the two ends and states a verdict. Allure deduplicates by
`historyId`: a test run twice within one results directory appears once, with
the earlier attempt kept as a retry. The number of distinct history ids is
therefore what a correct report should contain, and anything else is either a
stale report or results that were dropped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def expected_test_count(results_dir: Path) -> int:
    """Distinct tests in the results — retries collapsed, as Allure collapses them."""
    history_ids = set()
    loose = 0
    for path in results_dir.glob("*-result.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        history = data.get("historyId")
        if history:
            history_ids.add(history)
        else:
            loose += 1
    return len(history_ids) + loose


def reported_test_count(report_dir: Path) -> int | None:
    summary = report_dir / "widgets" / "summary.json"
    if not summary.exists():
        return None
    return json.loads(summary.read_text(encoding="utf-8"))["statistic"]["total"]


def main(results: str, report: str) -> int:
    results_dir, report_dir = Path(results), Path(report)
    expected = expected_test_count(results_dir)
    reported = reported_test_count(report_dir)

    if reported is None:
        print(f"  report check: no summary at {report_dir} — nothing was generated")
        return 1

    if reported == expected:
        print(f"  report check: OK — {reported} test(s) in the report, "
              f"{expected} distinct test(s) in the results")
        return 0

    print(
        f"  report check: MISMATCH — the report contains {reported} test(s) but the "
        f"results hold {expected}.\n"
        f"  A report is a snapshot of {results_dir} at the moment it was generated. "
        f"If a run finished afterwards, or the report was never regenerated, it "
        f"describes a different suite from the one that just ran — which is exactly "
        f"how a whole job goes missing from a report that looks complete.\n"
        f"  Regenerate before reading it."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
