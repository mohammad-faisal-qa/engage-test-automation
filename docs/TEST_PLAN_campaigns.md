# Test Plan — Campaigns

**Module:** Campaigns, including delivery and the analytics derived from it.
**Relates to:** [TEST_STRATEGY.md](TEST_STRATEGY.md) risks R2, R4, R6.
**Status:** implemented; 26 tests across four levels.

The campaign module is the one worth planning in detail because it is the only place where three
awkward properties meet: an irreversible state machine, an asynchronous side effect that leaves the
system, and derived numbers that people quote.

---

## 1. What the module does

A campaign is created as a **draft**, given a name, a channel and optionally a segment, and moves
through a guarded state machine:

```
draft ──> scheduled ──> running ──> sent
  │            │            ▲
  └────────────┴────────────┘        sent is terminal
```

Sending resolves the segment to an audience, creates one **delivery** per contact, and returns
`202 Accepted` before the work is done. The deliveries reach `sent` a moment later. A provider then
calls back with receipts — `delivered`, `opened`, `clicked`, `failed` — which arrive repeated and
out of order. Analytics counts each stage from *which timestamps are set*, not from a status string.

---

## 2. What can go wrong, and what it costs

| Failure | Business consequence | Detectable from a status code alone? |
|---|---|---|
| A campaign reports `sent` without sending | The funnel describes deliveries that do not exist; a manager reports success for a campaign nobody received | No — a 200 on the transition looks identical |
| The same receipt is applied twice | Analytics overstate delivery; a duplicate send would reach a customer twice | **No** — an endpoint that applies it twice also returns 200 |
| A late `delivered` overwrites an `opened` | The funnel reports more opens than deliveries; the dashboard is visibly nonsense | No |
| The audience resolves to the wrong people | The wrong customers receive a campaign. Unrecoverable — you cannot un-send | No |
| An empty segment sends to everyone | A campaign intended for a handful goes to the entire tenant | No |

Every row in that table is a case where the response is correct and the system is wrong. That single
observation determines the whole approach below.

---

## 3. Approach

**Assert on state, not on responses.** Each test performs the action, then reads the resulting rows
back and asserts on those. The idempotency test captures `delivered_at`, replays the identical
receipt, and asserts the timestamp is *unchanged* — a second 200 proves nothing.

**Never assert fixed numbers on shared data.** A campaign's audience is private to the test that
created it, so counts about *that* campaign are safe. Anything tenant-wide is asserted as an
invariant instead.

**Poll, never sleep.** Sending is asynchronous. The suite polls until no delivery is still queued —
"nothing is queued" rather than "everything says sent", because a failed delivery is also finished
and waiting for it to say `sent` would hang until timeout on a system that had already answered.

**Build the audience through the API.** A campaign test that created its contacts through the
browser would fail when the contact form broke.

---

## 4. Coverage

### 4.1 State machine — 6 tests · `api_tests/test_campaign_states.py`

| Case | Expected |
|---|---|
| A new campaign starts as a draft | `draft` |
| draft → scheduled | allowed |
| scheduled → draft | allowed (a mistake noticed before sending must be correctable) |
| draft → running → sent | allowed |
| **draft → sent** | **422, and the status is unchanged** |
| sent → anything | 422 for all three targets |
| A refusal names both states | the message contains `draft` and `sent` |

The last one is not decoration. "422 Unprocessable Entity" tells a caller nothing about which move
was refused, and that is the first thing anyone debugging needs.

### 4.2 Delivery and idempotency — 8 tests · `api_tests/test_delivery_idempotency.py`

Two independent defences, and a test for each:

- **The idempotency key** catches a provider retrying. Same payload, same key → the second call is
  a *replay*, and `delivered_at` does not move.
- **Stage timestamps** catch a provider retrying under a *fresh* key. `replayed` is false because
  the key was new; `applied` must still be false, because nothing was left to change.

Also covered: an async send polled to completion; receipts arriving out of order (`opened` before
`delivered`) leaving the status at `opened` rather than regressing; a missing `Idempotency-Key`
rejected with 400; a wrong secret rejected with 401 *and nothing applied*; an unknown delivery 404;
and a `failed` receipt recording its reason.

### 4.3 Analytics invariants — 4 tests · `api_tests/test_analytics_invariants.py`

Asserted as a shape that must always hold:

```
clicked ≤ opened ≤ delivered ≤ sent ≤ total
```

`sent == 5` is the tempting assertion and the wrong one — it passes today, breaks when the seed
changes, and would be satisfied by a funnel reporting 5 sent and 9 opened. The load-bearing test
posts `opened` *before* `delivered` and checks the shape still holds, which is precisely what the
application's timestamp-derived counting exists to guarantee.

### 4.4 Journeys — 4 scenarios · `features/campaign_lifecycle.feature`

Business outcomes a marketing manager could confirm: a campaign reaches everyone in its segment; it
cannot be reported as sent without being sent; a campaign with nobody to send to is refused; and
delivery outcomes are reflected in the results.

### 4.5 Interface — 3 tests

The campaign wizard is reachable and its steps are addressable (`pages/campaign_wizard.py`), and the
analytics dashboard is asserted against the intercepted payload rather than the rendered bars.

---

## 5. Environment and data

Runs against any instance over HTTP. Each test builds a two-contact cohort and a segment that
resolves to exactly those two — deliberately not the whole tenant, which on the seeded database
would be sixty deliveries per test and a much slower suite for no extra coverage.

`SEND_DELAY_SECONDS` (default 2.0) is what makes the send genuinely asynchronous. It is a feature of
the application, not an obstacle: without it, a test could assert on the response and appear to work.

---

## 6. Entry and exit

**Entry:** the delivery webhook is configured (`WEBHOOK_SECRET` set on both sides) — without it the
endpoint returns 503 and every idempotency test fails for a configuration reason rather than a
behavioural one.

**Exit:** all 26 green at `-n 4` three times; the funnel invariant holds in every analytics
assertion; and no test asserts a fixed tenant-wide count.

---

## 7. Known gaps in this module

- **Scheduled sends are not tested against time.** A campaign can be scheduled for a future
  timestamp; nothing here waits for it or manipulates the clock. The transition *into* `scheduled` is
  covered; firing on time is not.
- **Concurrent sends of the same campaign** are not tested. The 409 on a non-draft campaign implies
  a second send is refused, but two simultaneous first sends are not exercised.
- **Channel behaviour is not differentiated.** `email`, `sms`, `push` and `onsite` are accepted and
  stored; the application does not behave differently per channel, so no test pretends it does.
