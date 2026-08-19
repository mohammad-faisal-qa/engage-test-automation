# Engage — Test Automation

[![PR gate](https://github.com/mohammad-faisal-qa/engage-test-automation/actions/workflows/pr-gate.yml/badge.svg)](https://github.com/mohammad-faisal-qa/engage-test-automation/actions/workflows/pr-gate.yml)
[![Deployed smoke](https://github.com/mohammad-faisal-qa/engage-test-automation/actions/workflows/deployed-smoke.yml/badge.svg)](https://github.com/mohammad-faisal-qa/engage-test-automation/actions/workflows/deployed-smoke.yml)
[![Allure report](https://img.shields.io/badge/Allure_report-live-brightgreen)](https://mohammad-faisal-qa.github.io/engage-test-automation/)

API, contract, browser and BDD tests for **Engage**, a multi-tenant customer engagement platform.

| | |
|---|---|
| **Live test report** | <https://mohammad-faisal-qa.github.io/engage-test-automation/> |
| **Application under test** | [engage-app](https://github.com/mohammad-faisal-qa/engage-app) |
| **Live demo** | <https://engage-web-09fg.onrender.com> |

**138 tests** — 74 functional API, 24 contract, 24 browser, 16 BDD journeys — running green at
`-n 4` in about three and a half minutes.

The application is a separate repository on purpose, and nothing here imports a line of it. The
suite reaches the app the way any other client would: over HTTP, against a running instance. That
single constraint is what makes these tests meaningful — they agree with the application because it
behaves, not because they share its source.

---

## Quick start

The suite needs a running application. Start it from
[engage-app](https://github.com/mohammad-faisal-qa/engage-app):

```bash
cd <engage-app>/api && .venv/bin/uvicorn app.main:app --reload
cd <engage-app>/web && npm run dev          # only needed for the browser tests
```

Then here:

```bash
cp .env.example .env         # set TEST_API_KEY to the value the app was started with
make install                 # creates .venv, installs test dependencies
.venv/bin/playwright install chromium

make smoke                   # 3 tests, the critical-path gate
make all                     # everything, 4 workers
make report                  # open the Allure report
```

| Command | Runs |
|---|---|
| `make smoke` | fast critical-path gate (3) |
| `make api` | API suite, 4 workers (114) |
| `make ui` | browser suite, 2 workers (24) |
| `make all` | everything, 4 workers (138) |
| `make report` | serve the Allure report |
| `make clean` | wipe generated output |

A virtualenv is not optional — Homebrew's Python is `EXTERNALLY-MANAGED` under PEP 668, so a bare
`pip install` fails outright. `make install` handles it.

---

## How it is built

```
tests/
├── conftest.py         session fixtures: settings, database state, clients, failure hooks
├── config/settings.py  pydantic-settings — the one place the environment is read
├── clients/            service objects over httpx; base.py handles auth, logging,
│                       Allure attachment, retries and readable status failures
├── models/             the tests' own Pydantic response models
├── data/               factories.py (unique data) · constants.py (pinned seed facts)
├── utils/              waits.py (polling) · auth_state.py (cross-worker browser session)
├── api_tests/          functional and contract tests
├── pages/              page objects + components/ (nav, grid, rule builder, wizard, dialog)
├── ui_tests/           browser tests
├── features/           Gherkin — business journeys only
└── steps/              step definitions
```

---

## Design decisions

The parts worth explaining, because each one is a trade-off rather than a default.

### Parallel-safe from the first commit

Retrofitting parallel safety is far harder than building it in, so `-n 4` worked from Phase 1. Three
rules: the database resets **once per session**, guarded across xdist workers by a file lock; every
test creates uniquely-named data; and **no assertion depends on a global count**. `total == 40`
passes alone and fails in parallel on a system behaving perfectly — the most expensive kind of
failure, because it teaches people to re-run rather than read.

Segments needed more than that. They evaluate over every contact in the tenant, so each test stamps
a unique marker into `attributes.cohort` and every segment carries an `eq` condition on it —
membership is then exactly that test's contacts, whatever else is in the database.

### One registry fixture, not one fixture per identity

Three roles across two tenants is six identities, and by Phase 2 that would have been dozens of
near-identical fixtures. Instead `api.contacts(role="viewer")` reads as the identity under test, and
adding a service costs one method.

### The tests own their response models

Restating each response shape here, rather than importing the application's schemas, is what makes a
renamed field fail. Those models stay *tolerant of unknown fields* on purpose — adding a field is
backwards compatible and a functional test has no business failing over it.

Which is why contract tests exist separately: something still has to notice. They answer a different
question — *does the published contract still declare what this suite consumes?* — and the list of
what we consume lives here, in the consumer, so it can disagree with the provider. A list derived
from the provider would agree with it by definition.

### Assert on state, not on responses

An endpoint that rejects a write **after** committing it returns the same 403 as one that rejects it
properly. So the RBAC test checks the row is absent afterwards; the idempotency test captures
`delivered_at`, replays the receipt and asserts the timestamp did not move; the analytics tests
assert `clicked ≤ opened ≤ delivered ≤ sent` rather than any fixed number.

### Locators: user-facing first

`get_by_role` and `get_by_label` before `data-testid`, and CSS last. A testid lookup passes through
defects a person would trip over — a button that stops being a `<button>`, an input that loses its
label — so a suite built on testids alone reports green while the experience is broken. Testids earn
their place for per-row identity, where roles cannot express "the Delete button in contact 41's row".

### Failure evidence, only on failure

Screenshots, video and Playwright traces attach to Allure when a browser test fails and are
discarded when it passes. An artefact attached to everything is an artefact nobody opens.

### No sleeps, and no reruns

Every wait polls a condition with a timeout. No rerun plugin is installed, which makes the cheap
escape unavailable — the two intermittent failures we hit were fixed at the cause
([DEF-003](docs/defects/DEF-003-sticky-wait-always-succeeds.md),
[DEF-004](docs/defects/DEF-004-ci-only-connection-reset.md)) rather than absorbed.

---

## Continuous integration

| Workflow | Trigger | What it does |
|---|---|---|
| [`pr-gate.yml`](.github/workflows/pr-gate.yml) | push · PR | Builds the app from source against a `postgres:16` service container, boots it, polls `/api/health`, runs smoke → regression → destructive, publishes Allure |
| [`demo-reset.yml`](.github/workflows/demo-reset.yml) | 00:00 UTC | Restores the public demo to its seeded state; doubles as an uptime check |
| [`deployed-smoke.yml`](.github/workflows/deployed-smoke.yml) | 00:30 UTC | Runs the read-only subset against the deployed demo |

**The application is never pinned.** CI checks out `engage-app@main`, because a pinned application
would let this suite pass forever against a frozen target — the opposite of what a gate is for. The
SHA it actually tested is written into `environment.properties`, so a red build six months from now
still says which version it was red against.

**The two scheduled jobs are ordered deliberately.** `deployed-smoke` asserts the demo's seeded rows
are still what the suite expects, and the demo is public and writable — so the reset runs first at
00:00 and the checks at 00:30. Without that gap, a stranger clicking around would turn the alert
red, and an alert that cries wolf is one people stop reading.

**`readonly` is its own marker, never `smoke`.** They promise different things: `smoke` means *fast
and on the critical path*, `readonly` means *creates and mutates nothing*. Coupling them holds right
up until someone adds a smoke test that creates a contact — at which point the scheduled job starts
POSTing to the public demo with nothing to announce it. The claim is checked, not trusted: running
the readonly selection against a database we control leaves every row count identical.

---

## Documentation

| | |
|---|---|
| [TEST_STRATEGY.md](docs/TEST_STRATEGY.md) | Scope, risk matrix, levels, entry/exit, environments, and what we deliberately don't automate |
| [TEST_PLAN_campaigns.md](docs/TEST_PLAN_campaigns.md) | Feature-level plan for the campaign module |
| [METRICS.md](docs/METRICS.md) | What to track, and how each metric gets gamed |
| [docs/defects/](docs/defects/) | Real findings, with severity and priority set separately |
| [FRAMEWORK_BUILD.md](FRAMEWORK_BUILD.md) | The phase-by-phase build guide this repository was built from |

---

## Secrets

`.env` is gitignored and holds `TEST_API_KEY`, which guards the reset endpoint on a publicly
reachable demo. It must match the value the application was started with — in engage-app's `.env`
locally, and in the Render dashboard for the deployed instance. A mismatch surfaces as
`401 Missing or invalid X-Test-Key`, which reads like a broken test rather than a stale secret, so
the suite's precondition says so in as many words.

Request and response bodies are attached to every Allure report, so `clients/base.py` redacts
`Authorization`, `X-Test-Key` and `X-Webhook-Secret` before anything is written.
