# Test Framework — Phase-by-Phase Build Guide

**Repo:** `mohammad-faisal-qa/engage-test-automation` — the framework, and nothing else.
**App under test:** `mohammad-faisal-qa/engage-app`, checked out by CI at `main`. It is never
vendored here: one copy of the application exists, and the suite is always pointed at a running
instance of it over HTTP.
**Stack:** Python · pytest · Playwright · pytest-bdd · httpx · Pydantic · Allure · GitHub Actions
**Everything used here is free.** Public-repo Actions minutes and artifact storage are unmetered; Allure Report is open source (not Allure TestOps).

> **How to use this file.** Keep it in the repo root. Work one phase at a time — each has a
> copy-paste prompt at the end. **Do not start a phase until the previous one is green and
> committed.** That rule is the whole reason this is split into phases.

---

## Part 0 — Ground rules

These apply to every phase. Claude Code should treat them as constraints, not suggestions.

1. **Explain as you go.** After each phase: what was built, why that approach, and what an interviewer is likely to ask about it.
2. **Nothing is "done" until it runs.** Tests must actually pass, demonstrated, not asserted.
3. **Parallel-safe from day one.** Retrofitting parallel safety is far harder than building it in. See Part 2.
4. **Readable over clever.** The owner explains this code in job interviews. If a construct needs a paragraph to justify, use the simpler one.
5. **No sleeps.** Ever. Poll with a timeout instead.
6. **Where a decision has a real trade-off, present the options** rather than silently picking one.

**Commit at the end of every phase:**

```bash
git add . && git commit -m "test: phase N — <what>" && git push
```

---

## Part 1 — Target structure

```
tests/
├── conftest.py               root fixtures: settings, clients, auth, browser
├── requirements-test.txt
├── config/settings.py        pydantic-settings — base URLs, creds, timeouts
├── clients/                  Service Object Model (API)
│   ├── base.py               httpx wrapper: auth, logging, Allure attachment
│   ├── auth_client.py  contacts_client.py  segments_client.py
│   ├── campaigns_client.py   notifications_client.py  surveys_client.py
│   └── delivery_client.py    analytics_client.py
├── models/                   Pydantic response models (contact, segment, campaign, page)
├── pages/                    Page Object Model
│   ├── base_page.py  login_page.py  contacts_page.py  segments_page.py
│   ├── campaign_wizard.py  notifications_page.py  surveys_page.py  analytics_page.py
│   └── components/           nav · data_grid · rule_builder · wizard_stepper · modal
├── features/                 Gherkin — business journeys only
├── steps/                    step definitions
├── api_tests/                plain pytest, API
├── ui_tests/                 plain pytest, browser
├── data/                     factories.py · constants.py
└── utils/                    waits.py · db.py · auth_state.py

.github/workflows/tests.yml · demo-reset.yml
docs/  TEST_STRATEGY.md · TEST_PLAN_campaigns.md · METRICS.md · defects/
pyproject.toml · Makefile · README.md
```

---

## Part 2 — Cross-cutting design rules

### 2.1 Parallel safety

Four xdist workers share one database. Three rules:

- **Reset once per session, not per test.** Under xdist only one worker performs it, guarded by a file lock in `tmp_path_factory.getbasetemp().parent` (the only directory shared across workers).
- **Every test creates its own uniquely-named data** via `data/factories.py`, which stamps a UUID fragment into names and emails. Two workers can never collide.
- **Never assert on global counts.** `total == 40` breaks the instant another worker inserts a row. Assert your own record exists, or assert a delta you caused.

Escape hatch: `@pytest.mark.destructive` for the few tests needing exclusive state — run serially in a separate CI job.

### 2.2 Auth

- **API:** one token per role per session, cached.
- **UI:** Playwright `storage_state` — log in once, save to JSON, every context starts authenticated.
- **Across workers:** processes don't share memory, so write the state file to the shared temp dir under a `FileLock`. One worker logs in, the rest reuse.

### 2.3 BDD split

**If a non-technical stakeholder would read it, it's a feature file. Otherwise it's plain pytest.**

Roughly 20% Gherkin (business journeys), 80% pytest (CRUD, validation, negative cases, contracts, error states). Gherkin buys a translation layer that pays off on journeys and is pure overhead on `assert status_code == 422`.

### 2.4 Naming and markers

```toml
[tool.pytest.ini_options]
markers = [
  "smoke: fast critical-path gate",
  "regression: full suite",
  "api: API layer",
  "ui: browser",
  "e2e: BDD journeys",
  "contract: OpenAPI schema validation",
  "destructive: needs exclusive database state",
  "readonly: safe against a shared or deployed environment — creates and mutates nothing",
  "slow: over 10 seconds",
]
```

Test names describe behaviour, not mechanics: `test_viewer_cannot_create_contact`, not `test_post_contacts_403`.

---

# The Phases

---

## Phase 1 — Skeleton and first API tests

**Goal:** a working, parallel-safe test harness with five passing tests and a local Allure report.

**Build**

- `tests/requirements-test.txt` — pytest, pytest-xdist, pytest-bdd, playwright, pytest-playwright, httpx, pydantic, pydantic-settings, allure-pytest, filelock
- `tests/config/settings.py` — `API_BASE_URL`, `WEB_BASE_URL`, seeded credentials, `TEST_API_KEY`, timeouts; reads `.env`, defaults to localhost
- `tests/clients/base.py` — httpx wrapper: injects bearer token, logs request/response, attaches both to Allure, raises with a readable message on unexpected status
- `tests/clients/auth_client.py` and `contacts_client.py`
- `tests/models/` — `Contact`, `Page[T]`
- `tests/conftest.py` — session-scoped settings, per-role API clients (admin/editor/viewer × acme/globex), session reset under a file lock
- `tests/data/factories.py` — unique contact/segment/campaign builders
- `tests/utils/waits.py` — `poll_until(fn, timeout, interval)`
- `pyproject.toml` with markers, `Makefile`
- **Five tests** in `api_tests/`:
  1. login returns a token and `/auth/me` echoes the right tenant and role
  2. login with a bad password returns 401
  3. viewer is refused contact creation (403)
  4. acme token requesting a globex contact gets **404, not 403**
  5. contacts pagination returns a correct envelope and page 2 differs from page 1

**Done when**

```bash
make smoke                 # 5 passed
make smoke ARGS="-n 4"     # still 5 passed, no flakes
allure serve reports/allure-results   # report opens, requests attached
```

**Prompt**

> Read `FRAMEWORK_BUILD.md`. Build **Phase 1 only**.
>
> Create the `tests/` skeleton: pydantic-settings config, a `BaseClient` over httpx with auth injection and Allure request/response attachment, session-scoped auth fixtures for every role and tenant, `pyproject.toml` with the markers listed in Part 2.4, a Makefile, and the five API tests specified in Phase 1.
>
> Constraints: parallel-safe from the start (Part 2.1) — no reliance on global counts, unique data per test. Readable over clever; I explain this in interviews. No sleeps.
>
> When done, show me `make smoke` passing both serially and with `-n 4`, then explain the fixture chain: what's session-scoped, what's function-scoped, and why.

---

## Phase 2 — Full API suite

**Goal:** ~45 API tests across every module.

**Build**

- Remaining clients: segments, campaigns, notifications, surveys, delivery, analytics
- `api_tests/`:
  - `test_auth.py`, `test_rbac.py`, `test_tenant_isolation.py` — 12
  - `test_contacts_crud.py`, `test_contacts_pagination.py` — 10 (search, filters, page boundaries, invalid page, special characters)
  - `test_segments_rules.py` — 8 (**the interesting one**: `plan` is a column, `lifetime_value` lives inside JSONB — the evaluator must handle both; cover `all` vs `any`, every operator, empty results)
  - `test_campaign_states.py` — 6 (valid transitions, and rejecting `draft → sent`)
  - `test_delivery_idempotency.py` — 8 (**same payload twice, assert exactly one side effect**; out-of-order receipts; async send polled to completion)
  - `test_analytics_invariants.py` — 4 (opens ≤ deliveries ≤ sent, regardless of receipt order)

**Done when** `make api` is green serially and at `-n 4`, run three times consecutively with no flakes.

**Prompt**

> Phase 2 from `FRAMEWORK_BUILD.md`: the full API suite.
>
> Build the remaining service clients and the ~45 tests listed. Priorities: the segment evaluator tests must cover both column fields and JSONB attribute fields; the idempotency test must post the same payload twice and assert exactly one delivery; the analytics tests must assert invariants (opens ≤ deliveries ≤ sent) rather than fixed numbers.
>
> Async sends: poll with a timeout, never sleep.
>
> Run the suite three times at `-n 4` and show me it's stable before you call it done.

---

## Phase 3 — Contract tests

**Goal:** responses validated against the app's own published OpenAPI schema.

**Build**

- `api_tests/test_contract_openapi.py` — fetch `/openapi.json`, validate live responses for the main endpoints against their declared schemas
- Cover: required fields present, types correct, enums constrained, no undeclared fields on the critical models
- Add `@pytest.mark.contract`

**Done when** renaming a field in the app makes a contract test fail with a message naming the field.

**Prompt**

> Phase 3: contract tests against `/openapi.json`.
>
> Fetch the schema at session scope and validate live responses for contacts, segments, campaigns, delivery and analytics. Then prove it works: temporarily rename a response field in the app, show me the contract test failing with a useful message, and revert.
>
> Explain how this differs from the Pydantic model validation already in the clients — I need to be able to articulate why both exist.

---

## Phase 4 — Playwright foundation

**Goal:** browser tests running, authenticated, parallel-safe.

**Build**

- Playwright install and config; Chromium only for now
- `tests/utils/auth_state.py` — `storage_state` created once, shared across xdist workers under a `FileLock` in `tmp_path_factory.getbasetemp().parent`
- `pages/base_page.py` — navigation, `data-testid` locator helper, waits
- `pages/login_page.py`
- Failure hooks: screenshot, video and **Playwright trace** attached to Allure on failure
- Two tests: valid login, invalid login shows an error

**Done when** `make ui` passes at `-n 2`, and a deliberately failed test produces a trace you can open in the viewer.

**Prompt**

> Phase 4: the Playwright foundation.
>
> Set up Playwright (Chromium only), `storage_state` auth reuse shared across xdist workers via a file lock in the shared temp dir, a `BasePage` with `data-testid` helpers, a `LoginPage`, and pytest hooks attaching screenshot, video and trace to Allure on failure.
>
> Then break a test on purpose and show me the trace attached in the report.
>
> Explain the cross-worker sharing mechanism specifically — why an in-memory cache doesn't work under xdist, and what the lock is protecting.

---

## Phase 5 — UI suite

**Goal:** ~23 browser tests with page and component objects.

**Build**

- Components: `nav`, `data_grid`, `rule_builder`, `wizard_stepper`, `modal`
- Pages: contacts, segments, campaign wizard, notifications, surveys, analytics
- `ui_tests/`:
  - `test_contacts_grid.py` — 7 (paginate, search, filter, **deep-link straight to `#/contacts?page=3&q=…`**, back button, empty results)
  - `test_rbac_ui.py` — 3 (viewer sees no action buttons; direct URL to an edit route is refused)
  - `test_error_states.py` — 5 (**`route.fulfill` to force 500, timeout, empty list**, malformed payload — assert the UI degrades correctly)
  - `test_analytics_data.py` — 3 (**intercept `expect_response` and assert the payload behind the chart**, not the rendered bars)
  - `test_login.py` — 5

**Done when** `make all` is green at `-n 4`, three runs, no flakes.

**Prompt**

> Phase 5: the UI suite.
>
> Build the component objects and page objects listed, then the ~23 tests. Two things matter most: the error-state tests must use `route.fulfill` to force failures the app can't otherwise produce, and the analytics tests must assert on the intercepted API payload rather than the rendered chart.
>
> Use URL deep-linking to reach grid state instead of clicking there — the app supports it and it's faster and less flaky.
>
> Run everything three times at `-n 4` before calling it done.

---

## Phase 6 — BDD journeys

**Goal:** ~16 scenarios across 5 feature files, readable by someone non-technical.

**Build**

- `features/campaign_lifecycle.feature` — 4
- `features/segment_targeting.feature` — 3
- `features/onsite_frequency_cap.feature` — 4
- `features/survey_submission.feature` — 3
- `features/tenant_isolation.feature` — 2
- `steps/` — shared `common_steps.py` (login as role, seed data via API) plus per-feature steps
- Scenario Outlines where the same journey varies by data

**Done when** a non-tester could read a feature file and say whether it describes correct behaviour.

**Prompt**

> Phase 6: BDD journeys with pytest-bdd.
>
> Write the 5 feature files and step definitions listed. Rules: Gherkin describes **business outcomes**, never UI mechanics — "Then the campaign is delivered to everyone in the segment", not "Then I click the send button". All setup data comes from the API through existing clients, never through the UI.
>
> Show me one feature file and talk me through why each step is at the right level of abstraction.

---

## Phase 7 — CI and published reports

**Goal:** green badge, live Allure report with history, and a standing check that the deployed
demo is still alive.

This is the agreed design, in full, so it never has to be restated.

### Why two workflows and not one

The application is in another repository, and there are two entirely different questions to ask
about it. Keeping them in one workflow would blur them.

**`pr-gate.yml` asks "does this framework pass against the application as it is right now?"** It
builds the app from source against a throwaway database, so it may reset, truncate and rewrite
freely. It is the gate.

**`deployed-smoke.yml` asks "is the public demo still alive?"** It runs against the real Render
instance, which is a live demo someone may be looking at, so it may not write anything at all. It
is monitoring, not gating, which is why it runs on a schedule rather than on a push.

### `pr-gate.yml`

```
triggers      push · pull_request · workflow_dispatch
services      postgres:16 container (never Neon — no free compute burned, no
              dependency on an external tier being healthy)
checkout      engage-test-automation, plus engage-app at main into a subdirectory
install       engage-app/api/requirements.txt and tests/requirements-test.txt
boot          uvicorn against the service container, then poll /api/health until
              it answers — never sleep a fixed number of seconds

job 1  smoke        pytest -m smoke                                   fast gate
job 2  regression   pytest -m "not smoke and not destructive" -n 4    the bulk
job 3  destructive  pytest -m destructive                             serial
job 4  report       needs the test jobs · if: always()
                    merge allure results · restore history from gh-pages ·
                    publish to https://mohammad-faisal-qa.github.io/engage-test-automation/
```

**Do not pin the application to a commit.** Pinning would make the suite pass forever against a
frozen application, which is the opposite of what a gate is for — the job here is to notice when
the app moves underneath the tests. Check out `main`, and record which `main` you got: the SHA
goes into `environment.properties` so a red build says which application version it tested. A
failure six weeks later is then attributable instead of mysterious.

The report job runs `if: always()` because a failing run is exactly the one worth reading, and it
restores Allure history from `gh-pages` first, without which every report shows a single run and
trend and flaky detection never work.

### `deployed-smoke.yml`

```
triggers      schedule (daily) · workflow_dispatch
target        https://engage-api-b6yg.onrender.com
selection     pytest -m readonly
environment   RESET_DATABASE=false
              TEST_API_KEY from GitHub secrets
timeout       generous — see below
```

Two rules make this safe against a live demo, and the second is the one that is easy to get wrong:

- **`RESET_DATABASE=false`.** The deployed database is shared and public. Nothing here may wipe it.
- **`-m readonly`, never `-m smoke`.** They look interchangeable and are not: one of the smoke
  tests attempts a write. Pointing this job at `smoke` would have it POST to the public demo on a
  schedule. `readonly` is a promise a test makes about itself — creates nothing, mutates nothing —
  and it has to be claimed deliberately, which is the entire point of it being a separate marker.

Give it a **generous timeout**. The free Render instance sleeps after 15 minutes idle and takes
about a minute to wake, so the first request of the day is slow by design. A tight timeout turns a
perfectly healthy deployment into a red build and trains everyone to ignore the alert.

### README

Two badges: build status, and a link to the published report.

**Done when** a push produces a green badge and a live report URL; a deliberately failing test
still publishes; and the report's environment panel names the application commit that was tested.

**Prompt**

> Phase 7: CI and published Allure reports, across two repositories.
>
> Build `pr-gate.yml` and `deployed-smoke.yml` exactly as described above. The gate boots the app
> from `engage-app@main` against a postgres:16 service container and polls `/api/health`; it must
> not pin the app commit, and must record the SHA it tested in `environment.properties`. The
> deployed smoke job runs `-m readonly` with `RESET_DATABASE=false` against Render, with a timeout
> that survives a cold start.
>
> Explain why the deployed job uses its own marker rather than reusing `smoke` — I need to be able
> to say what would go wrong if it did.

---

## Phase 8 — The QA Lead documents

**Goal:** the written half of quality — what most candidates never produce.

**Build** in `docs/`

- **`TEST_STRATEGY.md`** — scope, risk matrix, test levels, entry/exit criteria, environments, tooling rationale, and **what we deliberately don't automate and why** (that section is the one that reads senior)
- **`TEST_PLAN_campaigns.md`** — feature-level plan for the campaign module: strategy down to specifics
- **`METRICS.md`** — what to track (escaped defects, automation coverage, flake rate, mean time to detect), what each tells you, and **how each gets gamed when used badly**
- **`docs/defects/`** — real defect reports from the exploratory session against the deployed app, in the format used on the portfolio site: summary, impact, repro, expected vs actual, root cause, **why testing missed it**, severity *and* priority separately
- **`README.md`** — architecture, design decisions with rationale, how to run, badges, screenshots

**Done when** a stranger can read the repo and understand both what it does and why it's built that way.

**Prompt**

> Phase 8: the documentation.
>
> Write `TEST_STRATEGY.md`, `TEST_PLAN_campaigns.md`, `METRICS.md`, and a proper `README.md`. The strategy must include a section on what we deliberately don't automate and why. The metrics doc must include how each metric gets gamed.
>
> For `docs/defects/`, use the real findings from my exploratory session — I'll paste them. Format them the way a QA Lead would: impact in business terms, root cause, and a "why testing missed it" section.

---

## Part 3 — Commands

```bash
make smoke     # pytest -m smoke
make api       # pytest -m api -n 4
make ui        # pytest -m ui -n 2
make all       # pytest -n 4
make report    # allure serve reports/allure-results
make clean     # wipe reports
```

---

## Part 4 — Known snags

| Symptom | Cause | Fix |
|---|---|---|
| `externally-managed-environment` | PEP 668 on Homebrew Python | Use the venv — `.venv/bin/pip`, never bare `pip3` |
| `allure: command not found` | CLI is separate from the pytest plugin | `brew install allure` (pulls Java) |
| Tests pass alone, fail at `-n 4` | Shared state | Re-read Part 2.1 — almost always a global-count assertion |
| Playwright browser missing in CI | Browsers aren't in pip | `playwright install --with-deps chromium` |
| Random 401s in CI | Token expiring mid-run | Widen `ACCESS_TOKEN_EXPIRE_MINUTES` for the test env |

---

## Part 5 — Stop points

**After Phase 3** you have a green, linkable, report-publishing API framework. That's the moment the Key Project claim on the resume becomes true — don't wait for Phase 8 to start applying.

**After Phase 7** the portfolio's last "Building" badge becomes a live report with a green CI badge.

**Phase 8 is what separates a QA Lead application from an SDET one.** Don't skip it.
