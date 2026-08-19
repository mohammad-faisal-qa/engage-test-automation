# Quality Metrics

What we track, what each number is actually evidence of, and — for each one — how it gets gamed.

The gaming section is not cynicism. Every metric here can be improved without improving anything
real, and in most teams that happens by accident long before anyone does it deliberately: a number
becomes a target, people optimise what they are measured on, and the measurement stops describing
the thing it was chosen to describe. Writing down the failure mode is the cheapest defence.

---

## 1. Escaped defects

**Definition.** Defects found after a change shipped, divided by all defects found for that change.

**What it tells you.** Whether testing is happening early enough to be worth what it costs. It is
the only metric here that measures the *outcome* rather than the activity, which is why it leads.

**How it gets gamed.**
- **Reclassify.** An escaped defect becomes "a change request" or "working as designed". The number
  improves and the customer's experience does not.
- **Stop looking.** Nobody triages production reports, so nothing is ever attributed to a release.
  Zero escaped defects and zero information.
- **Ship less.** The rate falls beautifully when releases stop.

**Reading it honestly.** Track the count *and* the denominator. A rate that improves while the total
number of defects found collapses is not a quality improvement, it is a detection collapse.

---

## 2. Automation coverage

**Definition.** For this suite: 138 tests across four levels — 74 functional API, 24 contract, 24
browser, 16 journeys — mapped against the ten risks in [TEST_STRATEGY.md](TEST_STRATEGY.md) §2.

**What it tells you.** Which risks have evidence behind them. Deliberately *not* line coverage of
the application: this repository does not import the application, and a percentage of lines executed
says nothing about whether the right assertions were made about them.

**How it gets gamed.**
- **Count tests instead of risks.** Two hundred tests that all exercise the login endpoint is a
  large number and a thin suite. This is the most common version, and it is usually accidental —
  tests accumulate where they are easy to write.
- **Assert nothing.** A test that calls an endpoint and checks it returned 200 counts identically to
  one that checks the row afterwards. Several of this suite's tests exist precisely because a status
  code was not enough: an endpoint that rejects a write *after* committing it returns the same 403 as
  one that rejects it properly.
- **Chase a line-coverage percentage.** The last 10% is almost always error handling that is
  cheapest to cover by asserting it does not crash — which is how a codebase reaches 95% coverage
  and still fails in every interesting way.

**Reading it honestly.** The useful question is never "what is our coverage" but "which risk in the
matrix has no test, and did we decide that or drift into it". [TEST_STRATEGY.md](TEST_STRATEGY.md)
§8 exists so the answer is written down.

---

## 3. Flake rate

**Definition.** Tests that produce different outcomes on unchanged code, as a share of runs. Allure
history makes this visible across runs; without history it is invisible by construction.

**What it tells you.** How much of the suite is still evidence. A flaky test does not merely waste a
rerun — it teaches everyone that red might mean nothing, and that lesson generalises to the tests
that were telling the truth.

**How it gets gamed.**
- **Retry until green.** The single most effective way to make this number zero while making the
  suite worthless. `--reruns 3` converts a real intermittent bug into a slow pass.
- **Quarantine.** Move flaky tests to a suite nobody blocks on. The rate improves; the coverage
  quietly leaves.
- **Delete.** Faster, and at least honest about what happened.

**Reading it honestly.** This suite has no rerun plugin installed, which is a deliberate constraint —
it makes the cheap escape unavailable. Two intermittent failures have occurred and both were fixed
at the cause rather than absorbed:

- a wait that always succeeded (`data-total` was sticky, so paging assertions could read the
  previous page and pass) — [DEF-003](defects/DEF-003-sticky-wait-always-succeeds.md)
- a connection reused after the server had already closed it, visible only in CI —
  [DEF-004](defects/DEF-004-ci-only-connection-reset.md)

---

## 4. Mean time to detect

**Definition.** From a defect being introduced to being observed. In practice: which gate caught it.

**What it tells you.** Whether the layers are ordered usefully. The suite is arranged so the
cheapest, most specific check fails first — a drifted seed constant fails 12 pinned tests rather
than scattering confusing failures across tenant isolation and campaign states.

**How it gets gamed.**
- **Measure from ticket creation.** Detection time then starts when someone writes it down, which
  measures administration, not detection.
- **Front-load trivia.** Adding a hundred fast assertions on things that never break improves the
  average and detects nothing.
- **Count only what was caught.** Defects nobody found have no detection time and silently leave the
  average.

**Reading it honestly.** Pair it with escaped defects. Fast detection of the things you catch, while
the rate of things you miss climbs, is a worse position than it looks.

---

## 5. Suite duration

**Definition.** Wall-clock for the full suite. Currently **~3 minutes 40 seconds at `-n 4`**
locally, ~20 seconds for the same tests in CI (where the database is in the same VM rather than
across the network).

**What it tells you.** Whether people will run it before pushing. A suite that takes twenty minutes
is a suite that runs after the fact, which changes it from a gate into a report.

**How it gets gamed.**
- **Delete slow tests.** Usually the integration ones, which are usually the ones finding things.
- **Raise parallelism until it is fast and flaky.** Shared state failures then appear, get blamed on
  "parallelism", and get fixed with reruns.
- **Skip on a marker in CI.** The suite is fast and the coverage is theatre.

**Reading it honestly.** Report duration alongside test count and pass rate. Getting faster while
the count falls is not an optimisation.

---

## 6. What we do not track, and why

**Test case count as a goal.** It measures typing. Reported as context for other numbers, never as
an objective.

**Defects found per tester.** It rewards volume and punishes whoever tests the risky area where each
finding costs a day. It also makes people compete over triage.

**Pass rate as a target.** The pass rate should be 100% and is otherwise information, not a score. A
team measured on pass rate will get one, and the cheapest route is not fixing code.

**Application line coverage, from this repository.** It would require importing the application,
which would break the property that makes these tests meaningful: they agree with the app only
because it behaves, not because they share its source.

---

## 7. Where the numbers come from

| Metric | Source |
|---|---|
| Automation coverage | Marker counts, mapped to the risk matrix by hand |
| Flake rate | Allure history on `gh-pages`, preserved across runs |
| Suite duration | pytest summary, per run, recorded in the report |
| Escaped defects | `docs/defects/`, with the "why testing missed it" section on each |
| Mean time to detect | Which gate caught it, recorded per defect |

Every published report also records the **application commit** it tested, so a number six months old
can still be attributed to a version of the product.
