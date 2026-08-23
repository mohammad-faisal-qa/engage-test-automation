# Engage — Test Automation

[![PR gate](https://github.com/mohammad-faisal-qa/engage-test-automation/actions/workflows/pr-gate.yml/badge.svg)](https://github.com/mohammad-faisal-qa/engage-test-automation/actions/workflows/pr-gate.yml)
[![Deployed smoke](https://github.com/mohammad-faisal-qa/engage-test-automation/actions/workflows/deployed-smoke.yml/badge.svg)](https://github.com/mohammad-faisal-qa/engage-test-automation/actions/workflows/deployed-smoke.yml)
[![Allure report](https://img.shields.io/badge/Allure_report-live-brightgreen)](https://mohammad-faisal-qa.github.io/engage-test-automation/)

A pytest framework — API, contract, browser and BDD — testing **Engage**, a multi-tenant customer
engagement platform, the way any other client would: over HTTP and through a browser, against a
running instance. The application is a separate repository and nothing here imports a line of it, so
these tests agree with it because it behaves, not because they share its source.

| | |
|---|---|
| **Live test report** | <https://mohammad-faisal-qa.github.io/engage-test-automation/> |
| **Live application** | <https://engage-web-09fg.onrender.com> |
| **Application under test** | [github.com/mohammad-faisal-qa/engage-app](https://github.com/mohammad-faisal-qa/engage-app) |

---

## Run it yourself

The suite tests a running application, so start one first.

```bash
# 1 · the application under test
git clone https://github.com/mohammad-faisal-qa/engage-app.git
cd engage-app
cp .env.example .env                 # set DATABASE_URL (any Postgres) and TEST_API_KEY
cd api && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload

# in a second shell — only needed for the browser tests
cd engage-app/web && npm install && npm run dev

# 2 · this repository
git clone https://github.com/mohammad-faisal-qa/engage-test-automation.git
cd engage-test-automation
cp .env.example .env                 # TEST_API_KEY must match the value the app was started with
make install                         # creates .venv, installs test dependencies
.venv/bin/playwright install chromium

make smoke                           # <!--n:smoke-->3<!--/n--> tests, the critical-path gate — seconds
make all                             # everything, 4 workers
```

**Expected:** `make all` reports **<!--n:without_db-->146<!--/n--> passed, <!--n:db-->5<!--/n-->
skipped** in just under four minutes. The skips are the database tests, which need
`TEST_DATABASE_URL` and skip cleanly without it — a fresh clone is green with no database of its own.
Set that variable and all <!--n:total-->151<!--/n--> run.

Most of those four minutes is network latency: a laptop talks to a hosted Postgres, so every request
pays a round trip. The same tests take about twenty seconds in CI, where the database is a container
on the same machine.

A virtualenv is not optional — Homebrew's Python is `EXTERNALLY-MANAGED` under PEP 668, so a bare
`pip install` fails outright. `make install` handles it.

| Command | Runs |
|---|---|
| `make smoke` | the critical-path gate |
| `make api` | everything with the `api` marker, 4 workers |
| `make ui` | the browser suite, 2 workers |
| `make db` | the database assertions (skips without `TEST_DATABASE_URL`) |
| `make all` | everything, 4 workers |
| `make report` | serve the Allure report |
| `make counts` | regenerate the numbers in this file |

---

## Architecture

```
tests/
├── clients/     Service Object Model — one object per API service, over httpx
├── pages/       Page Object Model + components/ (nav, grid, rule builder, wizard, dialog)
├── models/      the tests' own Pydantic response models
├── data/        factories (unique-by-construction) · constants (pinned seed facts)
├── utils/       waits · auth state · read-only SQL · safety guards · reporting
├── api_tests/   functional and contract tests
├── ui_tests/    browser tests
├── db_tests/    the few facts HTTP structurally cannot expose
├── features/    Gherkin — business journeys only
└── steps/       step definitions
```

**Service Object Model over httpx.** One object per service (`api.contacts()`, `api.campaigns()`),
each method in two flavours — `create()` asserts and returns a model, `create_response()` returns the
raw response for tests that are about a status code. A single registry fixture hands out any service
as any of six identities (three roles × two tenants), because a fixture per identity would have been
dozens of near-identical fixtures by the second phase. `clients/base.py` owns auth, logging, Allure
attachment with header redaction, connection pooling, and retries for idempotent methods only.

**Page Object Model for the browser layer**, with components for the parts that repeat — the data
grid, the rule builder, the campaign wizard, the confirm dialog. Locators are user-facing first
(`get_by_role`, `get_by_label`), `data-testid` second, CSS last: a suite built on testids alone stays
green while a button quietly stops being a button. Failure evidence — screenshot, video, Playwright
trace — attaches to Allure **only when a test fails**.

**BDD sits at the API layer, not the browser.** The journeys assert business outcomes — a campaign
reaches everyone in its segment, a capped notification stops being eligible — and those outcomes are
observable over HTTP. Running them through Playwright would make them slower and more fragile without
testing anything more, and would report a rendering fault when the rule engine was wrong. Gherkin
covers the scenarios a non-technical stakeholder would actually read; everything else is plain
pytest, because `assert status_code == 422` gains nothing from a translation layer.

**Two repositories, deliberately.** The framework cannot import the application even by accident, so
agreement between them is behavioural rather than structural — the tests restate every response shape
they depend on, and a renamed field fails here instead of quietly passing. The cost is real and worth
naming: CI checks out a second repository, and `TEST_API_KEY` lives in two places with nothing keeping
them in step, which is why a mismatch has its own explicit precondition message.

---

## What is in the suite

<!--table:groups-->
| Group | Count | What it answers | Selected by | Where |
|---|---:|---|---|---|
| Functional API | 75 | Does the application behave correctly? | `-m api`, minus contract | `tests/api_tests/` |
| Contract | 24 | Does it still promise what its clients depend on? | `-m contract` | `tests/api_tests/test_contract_openapi.py` |
| Browser (UI) | 24 | Does the interface work, and fail, correctly? | `-m ui` | `tests/ui_tests/` |
| BDD journeys | 16 | Do the business outcomes hold end to end? | `-m e2e` | `tests/features/` + `tests/steps/` |
| Database | 5 | Is the stored data right where no response could show it? | `-m db` | `tests/db_tests/` |
| Guard | 7 | Does the suite refuse to destroy what it protects? | `-m unit` | `tests/test_reset_guard.py` |
| **Total** | **151** | | `make all` | |
<!--/table-->

Every number above and in the quick-start is generated from a real pytest collection by
[`tests/utils/count_tests.py`](tests/utils/count_tests.py), and CI fails when this file disagrees
with the tests it describes. A hand-written count is wrong within a week, and a wrong number in the
first paragraph is the one claim a reader can check in ten seconds.

The suite is API-heavy on purpose. The interesting behaviour in this product is server-side — rule
evaluation, a state machine, idempotency, derived counts — and the interface gets tests for what only
the interface can be wrong about.

---

## Documentation

| | |
|---|---|
| [Test strategy](docs/TEST_STRATEGY.md) | Scope, a risk matrix, test levels, entry/exit criteria, environments and test-data rules |
| [Test plan — campaigns](docs/TEST_PLAN_campaigns.md) | Feature-level plan for one module, with its named gaps |
| [Defect reports](docs/defects/) | Five real findings, severity and priority set separately |
| [Metrics](docs/METRICS.md) | Five metrics, each with **how it gets gamed** |
| Decision records | The trade-offs, in the strategy: [tooling](docs/TEST_STRATEGY.md#7-tooling-rationale) · [what we don't automate](docs/TEST_STRATEGY.md#8-what-we-deliberately-do-not-automate) · [the database layer, argued both ways](docs/TEST_STRATEGY.md#9-the-database-assertion-layer) |
| [Build guide](FRAMEWORK_BUILD.md) | The phase-by-phase guide this repository was built from, amended where it diverged |

One of the five is a defect in this framework rather than the application — a wait that always
succeeded, so the suite could assert against the wrong page and pass. Another records a CI failure
whose first diagnosis was wrong and was shipped before being disproved. Both are written up as found,
because a defect log that only contains other people's mistakes is not a defect log.

---

## What this deliberately does not cover

Stated as decisions, because a coverage claim without its complement is half an answer. The full list
and the reasoning is in [§8 of the strategy](docs/TEST_STRATEGY.md#8-what-we-deliberately-do-not-automate).

- **Load, stress and soak.** The demo runs on a free tier that sleeps; any number produced would
  measure the host's cold start rather than the application.
- **Cross-browser.** Chromium only. Every extra browser multiplies run time and maintenance, and
  adding one should be a decision rather than a default.
- **Visual appearance.** No screenshot diffing — its failures are dominated by font rendering
  differences between a laptop and a CI runner. The *data* behind a chart is asserted instead, so a
  wrong number fails while a restyle does not.
- **The campaign wizard and rule builder through the browser.** Their page objects exist and nothing
  drives them. The risk each carries — a state machine, a rule evaluator — is covered directly at the
  API level. What that leaves genuinely untested is whether the form submits what the user selected.
- **Exhaustive field validation.** Boundaries are tested where a boundary means something;
  enumerating every string length would add hundreds of tests that all fail together on a library
  upgrade.
- **Retries as a way to pass.** No rerun plugin is installed, so the cheap escape is unavailable. The
  two intermittent failures found so far were fixed at the cause.

---

## Secrets

`.env` is gitignored. `TEST_API_KEY` guards the reset endpoint on a publicly reachable demo and must
match the value the application was started with; a mismatch surfaces as `401`, which reads like a
broken test rather than stale configuration, so the suite's precondition says so in as many words.
`TEST_DATABASE_URL` is deliberately a separate variable from the application's `DATABASE_URL` — the
database tests read only, and pointing them at a database is its own decision.

Request and response bodies are attached to every Allure report, so `clients/base.py` redacts
`Authorization`, `X-Test-Key` and `X-Webhook-Secret` before anything is written.
