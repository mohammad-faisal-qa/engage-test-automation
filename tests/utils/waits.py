"""Waiting, done the one acceptable way.

The rule is "no sleeps", and the distinction it draws is between *sleeping as a
synchronisation mechanism* and *sleeping between checks*. `time.sleep(3)` in the
hope that a send finished is banned: it is simultaneously too slow when the
system is fast and too short when the system is loaded, which is the recipe for
a flaky test that also wastes time. Polling asserts the condition, returns the
moment it holds, and fails with a stated timeout when it never does.
"""

from __future__ import annotations

import time
from typing import Callable, TypeVar

ResultT = TypeVar("ResultT")


class WaitTimeout(AssertionError):
    """A condition never became true inside its timeout."""


def poll_until(
    condition: Callable[[], ResultT],
    *,
    timeout: float = 30.0,
    interval: float = 0.25,
    message: str = "condition was never met",
) -> ResultT:
    """Call `condition` until it returns something truthy, then return it.

    Raises WaitTimeout, an AssertionError, so a timeout reads in the report as
    "the system never did the thing" rather than as a crash in the harness.
    """
    deadline = time.monotonic() + timeout
    attempts = 0
    last_result: ResultT | None = None

    while True:
        attempts += 1
        last_result = condition()
        if last_result:
            return last_result
        if time.monotonic() >= deadline:
            raise WaitTimeout(
                f"{message}\n"
                f"  waited:      {timeout:.1f}s\n"
                f"  attempts:    {attempts}\n"
                f"  last result: {last_result!r}"
            )
        time.sleep(interval)
