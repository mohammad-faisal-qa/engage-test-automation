# DEF-004 — Connection reset in CI only, and a wrong first diagnosis

| | |
|---|---|
| **Component** | engage-test-automation · `tests/clients/base.py` |
| **Severity** | Medium — intermittent CI failures on correct code |
| **Priority** | High — a gate that fails at random stops being read |
| **Status** | **Closed.** Root cause was [DEF-001](DEF-001-delete-contact-with-deliveries-returns-500.md), fixed in engage-app `438e9ca`. Framework mitigation retained. |
| **Found** | 2026-08-18, Phase 6, when the gate went red on a suite that had passed locally three times |

## Summary

Two consecutive CI runs failed with `httpx.ReadError: [Errno 104] Connection reset by peer` during
fixture setup for the delivery tests. The same commits passed locally three times at `-n 4`, and the
failure never reproduced locally even at `-n 8`.

## Impact

No product defect — the application was never observed misbehaving; the requests did not complete.
The cost is entirely to the gate's credibility:

- A red build on correct code trains people to re-run rather than read, and that habit does not
  distinguish between this failure and a real one.
- It arrived at exactly the wrong moment — immediately after a phase that added 16 tests — so the
  natural first assumption was that the new tests were bad.

## Why it only happened in CI

The two environments were not running the same experiment, which is the part worth remembering:

| | Local | CI |
|---|---|---|
| Database | Neon, across the network (~100 ms per query) | Postgres container in the same VM (sub-millisecond) |
| Cores | 10+ | 2 |
| Effect | Requests are slow and sparse | Requests are fast and dense — an order of magnitude more per second |

A suite that is I/O-bound on a remote database becomes CPU- and connection-bound on a local one.
"Passes locally" was never evidence about CI.

## The first diagnosis was wrong, and shipping it proved it

uvicorn closes an idle keep-alive connection after **5 seconds**; httpx's default `keepalive_expiry`
is also **5.0**. A genuine dead heat, and a real latent bug — a pooled connection can be picked up in
the same instant the server is closing it.

That fix was made, pushed, and **the gate failed again**, in the same place. The polling loop idles
250 ms between requests, nowhere near five seconds, so the race was never reachable on that path. The
change was worth keeping on its own merits and was not the cause.

The lesson: a plausible mechanism that explains the symptom is not the same as the mechanism that
produced it, and the cheapest way to tell them apart is to ship the fix and watch.

## What was done instead of a third guess

1. **Made the failure legible.** A transport error carried no URL, so the CI summary named neither
   the failing call nor which of several fixture requests died. Transport failures now report method
   and URL and state plainly that the request never completed — so it cannot be mistaken for the
   application refusing something.
2. **Retried only what is safe to retry.** `GET`, `HEAD` and `OPTIONS` are retried three times. `POST`,
   `PATCH` and `DELETE` are not: a write that reached the application and lost its response is
   indistinguishable from one that never arrived, and this client posts webhook receipts whose entire
   purpose is to be applied exactly once. Retrying them would undermine the very tests they serve.
3. **Made the server's side visible.** The gate now prints the uvicorn log when the tests fail.

## Current status, stated honestly

Three consecutive green runs followed — and **zero retry warnings fired in any of them**. So the
retry masked nothing, and equally the passes could not be attributed to the mitigation. The correct
claim at that point was: intermittent, handled, diagnosable, *not proven gone*.

## Then it recurred, and the diagnostics did their job

The very next push — **a documentation-only change** — failed the gate again. Nothing about the
suite had changed, which by itself ruled out the new tests. This time the error named the request:

```
clients.base.TransportFailure: DELETE http://127.0.0.1:8000/api/contacts/102
failed at the transport level after 1 attempt(s): ReadError: [Errno 104] Connection reset by peer
```

**That is not a test request at all.** It is the cohort fixture's *best-effort cleanup*, deleting a
contact after a delivery test — a contact that, by then, has deliveries referencing it.

Which makes this the same defect as
[DEF-001](DEF-001-delete-contact-with-deliveries-returns-500.md). Deleting a referenced contact hits
an unhandled `IntegrityError` in the application. Usually that surfaces as a `500`; under CI's
request density the connection is torn down mid-response instead, and because the call happens in
fixture teardown, it errors a test that had already passed.

Every previously puzzling detail follows from that single cause:

| Observation | Explanation |
|---|---|
| Only ever the delivery tests | They are the only tests whose contacts have deliveries |
| Reported as `ERROR`, never `FAILED` | It happens in teardown, after the test body succeeded |
| Never reproduced locally, even at `-n 8` | Against Neon the 500 path completes; the reset needs CI's timing |
| The keep-alive fix did not help | It was a real latent bug on a different path |
| The retry did not help | `DELETE` is deliberately not retried — correctly, and the log says `attempt 1/1` |

## Fix

Framework side: the cohort cleanup now swallows transport failures as well as bad statuses, with a
warning. That is not defensive programming for its own sake — cleanup is best-effort by definition,
and an exception raised in teardown must never fail a test that passed.

Application side: DEF-001 is now fixed in engage-app `438e9ca` — the unhandled exception that reset
the connection no longer occurs, so this failure mode has no source. The framework mitigation stays
anyway: cleanup should never be able to fail a run, whatever the application does.

## Why testing missed it

It was found by CI, which is where an environment-dependent failure can be found. The gap was that
**nothing in the local setup resembled CI's request density**, and nothing measured it. The suite ran
against a remote database on a fast machine and was assumed to be equivalent.

## Follow-up worth doing

- Run the suite locally against a containerised Postgres occasionally, to make the environments
  comparable rather than merely both green.
- If the reset recurs, capture uvicorn's log alongside it before changing anything else.
