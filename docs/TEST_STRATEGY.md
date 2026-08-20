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
| R1 | One tenant reads another's data | Catastrophic — contractual, and unrecoverable once it happens | Medium: every endpoint must remember to scope its query | 7 API tests + 1 BDD outline, per module, each with a control read; plus 3 storage checks for the tables HTTP cannot show (§9) |
| R2 | A delivery is sent twice | High — a customer receives the same message twice; trust is spent | High: providers retry callbacks by design | 8 API tests asserting *one side effect*, not one response, + 1 storage check that the side effect is one row (§9) |
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

151 tests. The shape is deliberate and is not a pyramid — it is a consequence of where this
application's risk actually sits.

| Level | Count | What it answers |
|---|---|---|
| Functional API | 75 | Does the application behave correctly? |
| Contract | 24 | Does it still promise what its clients depend on? |
| Browser (UI) | 24 | Does the interface work, and fail, correctly? |
| BDD journeys | 16 | Do the business outcomes hold end to end? |
| Guard (unit) | 7 | Does the suite refuse to destroy what it is protecting? |
| Database | 5 | Is the stored data right where no response could show it? |

The five database tests are the only ones that need something beyond a running application. Without
`TEST_DATABASE_URL` they skip and the other 146 run, so a clone with no database is still green — see
§9 for why they exist and the argument against them.

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

**The suite refuses to reset a production-looking target.** `GET /api/health` reports the database
endpoint label, and `database_state` will not reset when that label is production's or when the API
under test is the deployed instance — `ALLOW_PRODUCTION_RESET=true` is the deliberate override. The
label is exposed unauthenticated so the check works before a token exists; it names the database but
carries no host, role or credential, so it cannot be used to reach it. See DEF-005.

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

**The campaign wizard and the segment rule builder, through the browser.** Both page objects exist —
`CampaignWizard` and the `RuleBuilder` component — and nothing drives them. That has read as an
oversight for two phases, so here is the decision: they are not worth building now, and the reason is
that the risk they would cover is already covered where it actually lives.

The wizard is a four-step form over a state machine, and the state machine is the risky half: a
campaign must not go `sent → draft`, must not send twice, must not report as sent without sending.
Six API tests assert exactly that, directly, in about a second. Driving the same assertions through
four wizard steps would be slower, more fragile, and would report a rendering problem when the state
machine was wrong. The rule builder is the same shape: segment membership is computed, not stored, and
eight API tests cover both field kinds — a real column and a JSONB attribute — across every operator.
A browser test would re-ask a question already answered and couple the answer to a form.

**What that leaves genuinely uncovered**, stated plainly rather than implied: whether the form submits
what the user actually chose. The API tests prove the engine is right about a payload; nothing proves
the wizard builds that payload from the boxes on screen, or that the rule builder cannot compose a
condition it is unable to save. If a defect ever arrives where the UI sends something other than what
was selected, this paragraph is why it was missed.

**The condition for revisiting.** Either of those bugs appearing once, or the wizard gaining logic of
its own — conditional steps, client-side validation that the API does not repeat. Until then the two
page objects stay as the seam that makes those tests cheap to add, and they should not be counted as
coverage: an unused page object is scaffolding, not a test, and this document is the only thing
stopping an inventory from reading it as the latter.

**Anything requiring a real email or SMS provider.** Delivery is exercised through the webhook the
provider would call. Sending an actual message would make the suite depend on a mailbox, and the
part worth testing — what the system does with a receipt — is unchanged either way.

**Retries as a way to pass.** No test in this suite is marked flaky-and-retried. A test that needs a
rerun is a test that has stopped being evidence; the two we found were fixed at the cause (a wait
that always succeeded, and a connection reused after the server had closed it).

---

## 9. The database assertion layer

Five tests read the database directly. Every other test in this suite reaches the application over
HTTP and would rather not know a database exists, so this section says what changed, what constrains
it, and why a reasonable person might argue it should not exist at all.

### Why it exists

Three things this system can be wrong about have no HTTP representation whatsoever.

| Fact | Why HTTP cannot show it |
|---|---|
| Every row carries the tenant of the record it belongs to | `DeliveryOut` has no `tenant_id` field; `webhook_events` and `notification_impressions` have no endpoint at all |
| One idempotency key leaves exactly one stored event | `replayed: true` proves the *handler* deduplicated; it does not prove storage holds one row rather than two |
| A deleted contact leaves no row behind | A `404` is identical whether the row is gone or merely hidden behind a filter |

The first is the one that matters. Tenant isolation is already tested over HTTP as a *permission* —
acme asks for globex's record and is told it does not exist. That is a different promise from the
*storage* fact that the data was filed under the right owner to begin with, and a system can pass the
first while failing the second. When it does, nothing reports it: the API answers correctly about the
rows it can see, and the mis-stamped row stays invisible until it surfaces as one organisation's
analytics quietly counting another's sends.

### What was deliberately not written

Every candidate had to pass one test: **could an API response reveal this failure?** Where the answer
was yes, the check was dropped rather than written. Delivery rows are returned in full by
`GET /api/campaigns/{id}/deliveries`, so asserting on their contents here would duplicate the HTTP
layer and buy schema coupling for nothing. Segment membership, campaign state and analytics totals
are all visible over HTTP and all stayed there.

### The rules, and what enforces each

| Rule | Enforced by |
|---|---|
| Reads only. No writes, no schema changes, no cleanup through this path | **Postgres.** Every transaction opens `BEGIN READ ONLY`, so an `INSERT`, `UPDATE`, `DELETE` or `ALTER` is refused by the server — `cannot execute DELETE in a read-only transaction`. A statement check in `utils/db.py` catches the same mistake earlier with a clearer message, but the server is the guarantee |
| The guarantee has no autocommit hole | **Encapsulation.** Read-only is a property of a transaction, not of a connection: with autocommit on there is no transaction to have marked and a write succeeds. So the connection never leaves the module — the helper that opens it is private and `Database` exposes only reads, leaving no caller in a position to turn autocommit on |
| Its own URL — `TEST_DATABASE_URL`, never the application's `DATABASE_URL` | Configuration. Pointing the suite at a database is a separate, deliberate act from pointing the application at one |
| Unset means skip, not fail | A session fixture. A fresh clone runs green with no database in sight |
| CI points at the `postgres:16` service container, never Neon | The regression job is the only job that sets the variable, and it sets it to the same throwaway container the application is using |
| Every `db` test states in its docstring why the API cannot show this | A collection-time check that fails the run — `pytest.UsageError`, exit 4, nothing executes |

Two implementation notes, because the obvious approaches both fail and one of them fails
dangerously.

**A startup parameter does not survive a pooler.** `options=-c default_transaction_read_only=on` at
connect time is rejected outright by Neon's pooled endpoint as an unsupported startup parameter, and
every connection string in this project uses the pooled host.

**A session-level setting survives too well.** `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`
is the textbook fix for the autocommit hole, it works through the pooler, and it must not be used
here. A pooler multiplexes clients onto shared server connections, so the setting outlives the session
that issued it and is inherited by whoever is handed that connection next — including the application
under test. Setting it put the *application* into read-only sessions: `POST /api/test/reset` began
returning 500, and a brand-new connection opened by anyone reported `transaction_read_only = on`
until the pool was cleared. A test framework that can silently make the system under test read-only
is a worse problem than the narrow gap it was closing, which is why that gap is closed by keeping the
connection inside the module instead.

**The docstring rule is mechanical on purpose.** The risk this layer carries is not that these five
queries are wrong — they are short and they are checked. It is that the door is now open, and the
next person under time pressure reaches for SQL because it is quicker than making the API tell them.
A rule in a document depends on someone reading the document. This one fails the build.

### The honest argument against

It is a real argument and it is not fully answered.

**These tests know the schema, and the schema is not a contract.** Table and column names are
internal. `webhook_events.idempotency_key` can be renamed by a refactor that breaks nothing a client
depends on, and this suite will go red for it — a false failure, and the most expensive kind, because
it teaches people that red means "the tests need updating" rather than "the application is wrong".
Every other test here is insulated from that by construction, and these five are not.

**Rot is the more likely outcome than breakage** — a test coupled to storage stays green while the
meaning underneath it drifts. The clearest version of that was closed rather than accepted. The
tenant-stamp check originally queried each table whole, which a migration that backfilled `tenant_id`
across historical rows would satisfy: the check would keep passing while the handler that is supposed
to stamp new rows had stopped doing so. It now examines only the rows the test itself caused to exist
— a campaign sent to a private cohort, its deliveries, the receipt posted against one of them, an
impression on a notification created in the same fixture. Nothing can backfill a row created a moment
ago, so the assertion is about the write path rather than about stored state. What that gives up is
detection of a pre-existing mis-stamped row elsewhere in the table; that is a real loss and the lesser
one, because a broken write path produces such rows continuously and this catches the cause.

The residual coupling is to table and column *names*, and there is no clever way around it.

**What tips the balance.** The alternative is not "test it somewhere better" — it is *not testing it*,
because there is no HTTP surface to test it through. A cross-tenant storage bug is the single worst
failure in the risk matrix (R1) and the only one with no other detector. Five queries against three
table names is a small, visible coupling to accept for the one class of defect that would otherwise
ship silently.

**What would change the decision.** If the application ever exposed `tenant_id` on delivery
responses, or an admin endpoint over webhook events, the first two tests should be rewritten against
HTTP and this layer should shrink. It is meant to shrink. A database assertion layer that only ever
grows is a suite that has given up on its API.
