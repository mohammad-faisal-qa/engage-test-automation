# Test Strategy — Engage

**Product:** Engage, a multi-tenant customer engagement platform ([engage-app](https://github.com/mohammad-faisal-qa/engage-app))
**This document:** what we test, at which level, why that level, and what we deliberately leave alone.
**Owner:** Mohammad Faisal

---

## 1. Scope

### In scope

The application's HTTP API (42 endpoints across eight modules) and its browser interface, exercised
against a running instance over the network — the same way any other client reaches it.

| Module | Why it carries risk |
|---|---|
| Auth & tenants | Every authorisation decision derives from the token's claims |
| Contacts | The data every other module operates on |
| Segments | A rule engine; membership is computed, not stored |
| Campaigns | A state machine with an irreversible terminal state |
| Delivery & webhooks | Asynchronous, and receipts arrive repeated and out of order |
| Analytics | Derived numbers that people quote in decisions |
| Onsite notifications | Frequency capping, i.e. counting inside a rolling window |
| Onsite surveys | Validation of answers against a per-survey schema |

### Out of scope

- **Load, stress and soak.** The demo runs on a free tier that sleeps after fifteen minutes; any
  number we produced would measure Render's cold start, not the application.
- **Security testing beyond authorisation.** No injection fuzzing, no dependency CVE scanning. The
  authorisation and tenant-isolation boundaries *are* tested, because they are product behaviour.
- **Cross-browser.** Chromium only — see §7.
- **The application's own unit tests.** They live with the application. This repository tests it as
  a consumer would, and deliberately does not import a single line of it.

---

## 2. Risk matrix

Ranked by consequence, not by how easy each is to test. Coverage is stated so that the gaps are
visible rather than implied.

| # | Risk | Impact | Likelihood | Covered by |
|---|---|---|---|---|
| R1 | One tenant reads another's data | Catastrophic — contractual, and unrecoverable once it happens | Medium: every endpoint must remember to scope its query | 7 API tests + 1 BDD outline, per module, each with a control read |
| R2 | A delivery is sent twice | High — a customer receives the same message twice; trust is spent | High: providers retry callbacks by design | 8 API tests asserting *one side effect*, not one response |
| R3 | Segment selects the wrong people | High — the wrong audience receives a campaign | Medium: rules span a column and a JSON attribute | 8 API tests covering both field kinds and every operator |
| R4 | A campaign reports as sent without sending | High — the funnel describes deliveries that do not exist | Medium: any "mark as done" shortcut | 6 API tests on the state machine |
| R5 | Authorisation is wrong | High — a viewer writes, an editor deletes | Medium | 5 API + 3 UI tests, each with a positive control |
| R6 | Analytics report impossible numbers | Medium — decisions made on numbers nobody checks | Medium: counts derive from out-of-order events | 4 API tests asserting invariants, 3 UI tests asserting the payload |
| R7 | The published contract drifts from its clients | Medium — breakage lands in consumers, not here | Medium | 24 contract tests against `/openapi.json` |
| R8 | Frequency cap fails to cap | Medium — a visitor is pestered | Low | 4 BDD scenarios |
| R9 | The interface degrades badly when the API fails | Medium — a blank screen reads as "no data" | Medium | 5 UI tests forcing failures with `route.fulfill` |
| R10 | Survey accepts answers it declared invalid | Low — a summary built on nonsense | Low | 3 BDD scenarios |

**R1 and R2 drive the design of the suite.** Both are cases where a single response looks correct
and the system is still wrong, which is why those tests assert on state after the fact rather than
on the status code.

---

## 3. Test levels

138 tests. The shape is deliberate and is not a pyramid — it is a consequence of where this
application's risk actually sits.

| Level | Count | What it answers |
|---|---|---|
| Functional API | 74 | Does the application behave correctly? |
| Contract | 24 | Does it still promise what its clients depend on? |
| Browser (UI) | 24 | Does the interface work, and fail, correctly? |
| BDD journeys | 16 | Do the business outcomes hold end to end? |

**Why API-heavy.** The interesting behaviour in this product is server-side: rule evaluation, a
state machine, idempotency, derived counts. Testing those through a browser would be slower, more
fragile, and would report a rendering problem when the rule engine was wrong. The interface gets
tests for what only the interface can be wrong about.

**Why BDD is 12% and not 100%.** Gherkin buys a translation layer, and that layer is worth its cost
on journeys a non-technical stakeholder would want to confirm — "the campaign reaches everyone in
its segment". It is pure overhead on `assert status_code == 422`. The rule we apply: *if a
stakeholder would read it, it is a feature file; otherwise it is plain pytest.*

**Why contract tests are separate from the client models.** The clients' Pydantic models tolerate
unknown fields on purpose — adding a field is backwards compatible, and a functional test has no
business failing because the app grew a column. Somebody still has to notice, and that is the
contract suite's job. The two answer different questions: *is what I depend on present and the right
type?* versus *does the published contract still match what I was promised?*

---

## 4. Entry and exit criteria

**Entry to a test cycle**

- The application is deployable and `/api/health` reports its database reachable.
- Seed data is restorable in one call (`POST /api/test/reset`).
- The OpenAPI document is published — contract tests have nothing to check against otherwise.

**Exit — a change may ship when**

1. The full suite is green at `-n 4`, three consecutive runs, no reruns.
2. No test was skipped or quarantined to achieve that.
3. New behaviour arrived with tests at the level that matches its risk (see §2).
4. Any new defect is either fixed or written up with severity and priority set separately.
5. The published Allure report names the application commit that was tested.

**Point 2 is the one that gets negotiated away.** A suite kept green by disabling tests is worse
than a red one, because it still reports.

---

## 5. Environments

| Environment | Database | Used for | Reset? |
|---|---|---|---|
| Local | Neon `test` branch | Development of tests | Yes, once per session |
| CI (PR gate) | `postgres:16` service container | Every push and pull request | Yes, per run |
| Deployed demo | Neon `production` branch | Scheduled read-only monitoring | Never by the suite |

Three decisions worth defending:

**Postgres everywhere, never SQLite.** `LIKE` is case-sensitive in Postgres and not in SQLite, so
contact search behaves differently; and Postgres sequences do not advance when a seed inserts
explicit ids, so the first API-created row collides with a seeded one. Both bugs are invisible until
deployment. The same engine on both sides removes the class entirely.

**A service container in CI, not Neon.** CI must not burn a free compute budget, and a gate that
depends on an external tier being awake is a gate that fails for reasons unrelated to the change.

**The demo's database is separated from local development.** Local runs previously reset the same
Neon branch the public demo served, so running the suite wiped the demo the portfolio links to. A
`test` branch now backs local runs; the deployed instance keeps `production`, and the only job
permitted to write to it is the nightly reset.

---

## 6. Test data

Every test creates the data it needs and refers to nothing it did not create or explicitly pin.

- **Uniqueness by construction.** Factories stamp a UUID fragment into names and emails, so two
  workers running the same test cannot collide.
- **Cohort markers.** Segments evaluate over every contact in the tenant, so a segment matching
  `plan = enterprise` would also match the seeded forty. Each test stamps a unique marker into
  `attributes.cohort` and every segment carries an `eq` condition on it — membership is then exactly
  that test's contacts.
- **Never assert a global count.** `total == 40` passes alone and fails at `-n 4` on a system
  behaving perfectly. Assert your own record exists, or a delta you caused.
- **Setup through the API, never the interface.** A journey about frequency capping should fail when
  capping breaks, not when the form that creates a notification breaks.

Seeded facts the suite pins (contact 41 is globex's, campaign 3 is the sent one) are themselves
tested — 12 tests assert `data/constants.py` still describes the application's seed, so drift fails
once, loudly, instead of scattering.

---

## 7. Tooling rationale

| Choice | Why | What we gave up |
|---|---|---|
| pytest | The team's language; fixtures model setup/teardown honestly | — |
| pytest-xdist | The suite is I/O-bound; `-n 4` turns 12 minutes into 3 | Parallel safety must be designed in, not retrofitted |
| httpx | Sync client, explicit connection pooling, readable errors | — |
| Pydantic | Response models that fail where the shape is wrong, not three asserts later | — |
| Playwright | Auto-waiting locators, `route.fulfill`, and traces that make a CI failure debuggable | — |
| pytest-bdd | Gherkin for the 12% that earns it | A second way to write a test; kept deliberately small |
| Allure | History, trends and flaky detection across runs; attachments on failure | A Java dependency in CI |
| GitHub Actions | Free for public repositories, and the app already deploys from GitHub | — |
| Chromium only | Every browser multiplies run time and maintenance | Cross-browser bugs. Accepted: this is a demo, and adding browsers is a decision to take deliberately, not by default |

---

## 8. What we deliberately do not automate

The most useful section in this document, because everything above is a claim about what we cover,
and this is a claim about what we have decided not to.

**Exploratory testing of new features.** Automation checks what someone already thought of. It has
never once found a problem nobody imagined, because a test is a written-down expectation. The first
pass over anything new is a person using it with intent, and the output of that session is bugs plus
*new tests* — in that order. Automating first would encode the same blind spots faster.

**Visual appearance.** No screenshot diffing. The failure rate of pixel comparison is dominated by
font rendering and antialiasing differences between a laptop and a CI runner, and the true positives
it finds are mostly things a person notices in seconds. What we do instead is assert on the *data*
behind a chart, so a wrong number fails while a restyle does not.

**Third-party behaviour.** Neon, Render and GitHub Actions are dependencies, not features. Testing
that Render serves a static file tests Render. The one exception is the scheduled check that the
deployed demo is alive, which is monitoring rather than testing, and is labelled as such.

**Every field's validation, exhaustively.** Boundary tests exist where a boundary carries meaning —
page size, rating range, the two-letter country code. Enumerating every string length on every field
would add hundreds of tests that all fail together whenever the validation library is upgraded, and
none of which describe a risk anyone accepted.

**The onsite notification and survey editors, through the browser.** Both are covered at the API and
journey levels, where their logic lives. Their forms are the least risky part of the product and the
most expensive to test through a browser. This is a coverage gap and it is a chosen one; if
capping ever breaks in a way only the form can cause, this decision is why we missed it.

**Anything requiring a real email or SMS provider.** Delivery is exercised through the webhook the
provider would call. Sending an actual message would make the suite depend on a mailbox, and the
part worth testing — what the system does with a receipt — is unchanged either way.

**Retries as a way to pass.** No test in this suite is marked flaky-and-retried. A test that needs a
rerun is a test that has stopped being evidence; the two we found were fixed at the cause (a wait
that always succeeded, and a connection reused after the server had closed it).
