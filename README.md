# Engage — Test Automation

API and UI test automation for **Engage**, a customer engagement / campaign platform.

| | |
|---|---|
| Application under test | [engage-app](https://github.com/mohammad-faisal-qa/engage-app) |
| Live demo | <https://engage-web-09fg.onrender.com> |
| API docs | <https://engage-api-b6yg.onrender.com/docs> |

The application is a separate repository on purpose. This one holds only the framework, and it
reaches the app the way any client would — over HTTP, against a running instance. Nothing here
imports application code, which means these tests cannot accidentally agree with the app by
construction: if a response shape changes, the suite finds out the same way a real consumer would.

## Status

**Phase 1 complete** — a parallel-safe harness with five API tests.

| Phase | Scope | State |
|---|---|---|
| 1 | Harness, config, service clients, first five API tests | Done |
| 2 | Full API suite across every module | Not started |
| 3 | Contract tests against `/openapi.json` | Not started |
| 4 | Playwright foundation | Not started |
| 5 | UI suite | Not started |
| 6 | BDD journeys | Not started |
| 7 | CI and published Allure reports | Not started |
| 8 | Strategy, plan, metrics and defect documents | Not started |

The full plan, phase by phase, is in [FRAMEWORK_BUILD.md](FRAMEWORK_BUILD.md).

## Running it

The suite needs a running application. Start it from the
[engage-app](https://github.com/mohammad-faisal-qa/engage-app) repository:

```bash
cd <engage-app>/api
.venv/bin/uvicorn app.main:app --reload
```

Then, here:

```bash
cp .env.example .env         # set TEST_API_KEY to the value the app was started with
make install                 # creates .venv and installs test dependencies
make smoke                   # the critical-path gate
make smoke ARGS="-n 4"       # the same tests, four workers, no flakes
make report                  # opens the Allure report
```

A virtualenv is not optional: Homebrew's Python is marked `EXTERNALLY-MANAGED` under PEP 668, so a
bare `pip install` fails outright. `make install` handles it.

| Command | What it runs |
|---|---|
| `make smoke` | fast critical-path gate |
| `make api` | API suite, 4 workers |
| `make ui` | browser suite, 2 workers |
| `make all` | everything, 4 workers |
| `make report` | serve the Allure report |
| `make clean` | wipe generated output |

## How it is built

```
tests/
├── conftest.py         session fixtures: settings, database state, clients
├── config/settings.py  pydantic-settings — one place the environment is read
├── clients/            service objects over httpx; base.py handles auth,
│                       logging, Allure attachment and readable status failures
├── models/             the tests' own Pydantic response models
├── data/               factories.py (unique data) · constants.py (seed facts)
├── utils/              waits.py — polling, never sleeping
├── api_tests/          plain pytest
├── ui_tests/           browser tests (Phase 4+)
└── features/ steps/    BDD journeys (Phase 6)
```

Three decisions are worth the space:

**Parallel-safe from the first commit, not retrofitted.** The database is reset once per session
rather than once per test, and under `-n 4` exactly one worker performs it, guarded by a file lock
in the only directory the workers share. Every test builds its own uniquely-named data, and no
assertion depends on a global count — `total == 40` would pass alone and fail in parallel, on a
system that is behaving correctly.

**One registry fixture, not one fixture per identity.** Three roles across two tenants is six
identities, and by the end of Phase 2 that would have been dozens of near-identical fixtures.
Instead `api.contacts(role="viewer")` reads as the identity under test, and adding a service costs
one method.

**Tests own their response models.** Restating the shape here rather than importing the app's
schemas is what makes a renamed field fail. Those models stay tolerant of *unknown* fields, because
adding one is backwards-compatible; proving the whole published contract is the separate job of the
OpenAPI contract tests in Phase 3.

## Secrets

`.env` is gitignored and holds `TEST_API_KEY`, which guards the reset endpoint on a publicly
reachable demo. It must match the value the application was started with — in engage-app's own
`.env` locally, and in the Render dashboard for the deployed instance. Request and response bodies
are attached to every Allure report, so `base.py` redacts `Authorization`, `X-Test-Key` and
`X-Webhook-Secret` before anything is written.
