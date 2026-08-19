# DEF-003 — A wait that always succeeded, in our own framework

| | |
|---|---|
| **Component** | engage-test-automation · `tests/pages/components/data_grid.py` |
| **Severity** | High — the suite could report green while asserting against the wrong page |
| **Priority** | High — false confidence is the most expensive kind of defect a test framework can have |
| **Status** | **Fixed** in `809da2d` |
| **Found** | 2026-08-18, Phase 5, by two tests failing on their first run |

## Summary

`DataGrid.expect_loaded()` waited for the pager's `data-total` attribute to exist. That is a correct
signal for a *first* load and meaningless afterwards, because the attribute is never cleared — after
a page change it is already set, so the wait returned immediately, before the new rows had rendered.

## Impact

This is a defect in the test framework, so its impact is measured in wrong verdicts rather than
wrong behaviour — and the direction is the dangerous one.

Any assertion made after a page transition could read the **previous** page and pass. The paging
test would have compared page 1 against page 1 and found them identical, which is exactly what a
correctly-working grid produces when you look too early. Had the assertion been written the other way
round — "the ids should be the same after going back" — it would have passed for the wrong reason
and stayed passing through any regression in paging.

**A wait that always succeeds is worse than no wait**, because no wait fails loudly and immediately
while a sticky one produces a suite that is green and not measuring anything.

## How it showed up

Two tests failed on their first run:

```
assert contacts.grid.row_ids() != first_page_ids
E   assert [1, 2, 3, 4, 5, 6, ...] != [1, 2, 3, 4, 5, 6, ...]
```

Both were assertions that pages *differ*. They failed honestly, which is the only reason the flaw
was visible at all.

## Root cause

```python
# before
self.page.wait_for_function(
    "prefix => { const el = ...; return el && el.dataset.total !== undefined }", ...
)
```

The condition asks "has this grid ever loaded", not "has this grid loaded the thing I just asked
for". Every state-change wait must be able to distinguish the new state from the old one; this one
could not, by construction.

## Why testing missed it

It did not — it failed on first use. What is worth recording is *why it was written that way*: the
helper was created during Phase 4, when the only browser tests were logins with a single page load.
Under that usage the wait was correct, and it stayed correct until the first test that changed pages,
one phase later.

The general shape: **a synchronisation helper is only as good as the transitions it has been used
for.** Ours was written against a single transition and silently generalised to all of them.

## Fix

`expect_loaded()` remains, restricted to first loads and documented as such. Two discriminating
waits were added:

- `expect_page(n)` — waits for the pager text to name the page, which differs between states. Safe
  because the application writes the pager text and the rows in one synchronous block.
- `expect_row_count(n)` — an auto-waiting count assertion, rather than `row_ids()`, which snapshots
  whatever is in the DOM at that instant.

## Preventive note

`row_ids()` is a snapshot and cannot wait — that is inherent to reading a list of values rather than
asserting a condition. Every call to it should be preceded by a wait that distinguishes the state it
is being read in. The method's docstring now says so.
