# DEF-005 — Local and live were configured against database endpoints never verified as distinct

| | |
|---|---|
| **Component** | Environment configuration — `~/engage-app/.env` (untracked), Neon project `engage` |
| **Severity** | **High** — not because local runs are blocked, but because the same misconfiguration in the other direction wipes the production demo. See *Impact*. |
| **Priority** | **High** — acted on: the guard is built and tested (see *Guardrail*) |
| **Status** | **Root cause established. Guarded, not merely reported** — the suite now refuses to reset a production-looking target (`tests/utils/safety.py`, 7 tests). Environment restored on a new test branch. |
| **Found** | 2026-08-19, while writing `PROJECT_INVENTORY.md` — by trying to read row counts, not by any test |

## Summary

`~/engage-app/.env` carries the `DATABASE_URL` the locally-run API opens. That single line decides
which database the entire local test suite reads *and writes*, including whether
`POST /api/test/reset` wipes a throwaway copy or the live demo.

On 2026-08-18 that line was pointed at endpoint `ep-silent-shape-ax7q77lk`, believed to be a
dedicated `test` branch. Since 2026-08-19 that endpoint has rejected the credential, and the local
API reports `{"status":"degraded","database":"unreachable"}`. The live demo, on endpoint
`ep-round-snow-axyc70lw`, accepts the *same* credential and is unaffected.

At the time, the two endpoints had been verified as distinct only by a one-off manual probe, and
nothing checked it afterwards. A guard now does, on every reset.

## Impact

**The blocked local environment is the mild half.** No test can run locally; that is visible,
loud, and costs a day.

**The severe half is the same mistake in the other direction.** `settings.reset_database` defaults
to `True`, and the interim `RESET_DATABASE=false` stopgap was removed on 2026-08-18 once the
databases were believed to be separate. Verified today:

```
settings.reset_database resolves to: True
=> make all WILL call POST /api/test/reset against whatever the local API points at
```

So if `~/engage-app/.env` names the production endpoint — by a paste, a rollback, a restored
backup of the file, or simply by someone fixing a broken local environment with the connection
string that is known to work — then the next `make all` wipes and re-seeds the public demo the
portfolio links to. No confirmation prompt stands in the way, because from the framework's side
this is indistinguishable from a normal run.

**This is not hypothetical.** It is exactly what happened before the split: local runs reset the
same Neon database the deployed demo served, which is *why* a test branch was introduced. The
current failure mode is that arrangement quietly coming undone.

Nothing in either repository, in `render.yaml`, or in CI constrains this — verified:

| Where | Constrains the local database? |
|---|---|
| `engage-app` tracked files | No — 0 files reference either endpoint |
| `engage-test-automation` tracked files | No — 0 files; the suite has no `DATABASE_URL` at all |
| `render.yaml` | No — `DATABASE_URL` is `sync: false`, set by hand in the Render dashboard |
| CI (`pr-gate.yml`) | No — uses a `postgres:16` service container on `127.0.0.1` |

The blast radius is therefore decided entirely by one line in one untracked file on one laptop.

## Evidence

**What is established:**

- On 2026-08-18 the two endpoints were reachable *and held different data.* Proven by writing to
  one and reading the other: a marker row inserted at `ep-silent-shape` took its contact count
  60 → 61 while `ep-round-snow` stayed at 60, and the marker was not visible there. Two databases,
  not one, at that moment.
- Since 2026-08-19, `ep-silent-shape` returns `password authentication failed for user
  'neondb_owner'`. `ep-round-snow` accepts the identical credential — so the credential itself is
  not the variable.
- The `.env` line has not changed since 2026-08-18 14:45 (file mtime), and its password
  fingerprint is unchanged.
- **The error cannot distinguish a wrong password from an unroutable endpoint.** Probing that
  endpoint with the real credential and with deliberate garbage produces the same error class.
- Both hostnames still resolve in DNS, to Neon proxy addresses. DNS therefore says nothing about
  whether a branch exists behind them.

**What Neon documents.** Their connection-errors page attributes `password authentication failed`
to *"incorrectly defined connection information, or the driver you are using does not support
Server Name Indication (SNI)"*, and documents a **separate, explicit** error for a missing endpoint
ID (`The endpoint ID is not specified…`). Neon does **not** document that a deleted or unroutable
endpoint surfaces as an authentication failure.

## Root cause

**Established.** The Neon project `engage` has exactly two branches:

| Branch | Parent | Created | Endpoint |
|---|---|---|---|
| `production` | — (default) | at project creation | `ep-round-snow-axyc70lw` |
| `test` | `production` | 2026-08-20 | `ep-falling-firefly-axrf9s08` |

The endpoint in the old `.env`, **`ep-silent-shape-ax7q77lk`, belongs to neither.** It was a third
branch, and it was deleted. That is why the connection stopped working, and it is why no credential
would have fixed it.

It was a real branch and not a replica of production: the probe on 2026-08-18 wrote a row through
one endpoint and could not see it through the other, and the contact counts diverged 60 → 61 while
production stayed at 60. Two databases, confirmed by observation at the time.

So the failure had nothing to do with the password, which is precisely what made it expensive.

## One error message, three different causes

`password authentication failed for user 'neondb_owner'` appeared three times in this project, from
three unrelated causes. **Not one of them was a wrong password.**

| # | What was actually wrong | Why the message misleads |
|---|---|---|
| a | **The branch had been deleted.** The endpoint in the connection string no longer belonged to anything. | There is nothing to authenticate against, so the proxy reports an authentication failure rather than "no such endpoint". |
| b | **A child branch silently kept the parent's old password.** A branch inherits its parent's roles *and their passwords as they were at branch time*, and does not track later changes. Reset the parent's password afterwards and the child still expects the old one. | Both branches are healthy and reachable. The credential is simply correct for a different branch than the one being dialled. |
| c | **The wrong page was used to rotate the credential.** Neon's left-hand *Credentials* page manages S3 and AI Gateway tokens; Postgres roles live under **Branch → Roles**. Resetting on the former changes nothing about Postgres. | The rotation appears to succeed, and the old password keeps failing — which reads as "the reset did not take". |

All three are **topology or lifecycle faults**. None is a credential fault. The message points at
the password every time, and it was never the password — that ambiguity is the actual content of
this defect, and it cost roughly a day across two investigations plus one wrong published
hypothesis.

Neon's own documentation does not disambiguate: it attributes the message to *"incorrectly defined
connection information, or the driver you are using does not support SNI"*, and documents a
separate, explicit error only for a **missing** endpoint ID. Verified here that the error is
identical whether the credential is right or deliberate garbage, so the message cannot be used to
tell the two apart.

**Rejected hypothesis, recorded so nobody re-runs it:** that scale-to-zero restored a control-plane
credential and discarded a manual `ALTER USER`. It does not fit a project whose branch list never
contained the endpoint in question, and no documentation was found supporting the mechanism.

## Why testing missed it

Nothing tests the environment. The suite has 138 tests covering the application and zero covering
the configuration it runs against.

Specifically:

- **Nothing monitors local environment health.** `deployed-smoke.yml` watches the deployed demo
  every morning; there is no equivalent for a developer's machine, and there is no reason there
  would be — so a local environment can rot silently and only announce itself when someone next
  tries to work. This one broke on the 19th and was noticed on the 19th only because a document
  needed row counts.
- **Nothing asserts the two databases are distinct.** The isolation probe that proved it on the
  18th was a one-off script, not a test. Had it been a test — even one `readonly` check that the
  local API is not pointed at the production endpoint — it would have failed on the 19th with a
  clear message instead of the suite failing with `database: unreachable`.
- **The framework cannot see the risk it carries.** It knows `API_BASE_URL` and nothing about which
  database sits behind it, so it cannot refuse to reset a production database; `/api/health` reports
  only `connected` or `unreachable`.

## If this happens again

**First: assume the topology is wrong, not the credential.** `password authentication failed` has
been produced three times in this project by a deleted branch, by a child branch holding its
parent's old password, and by rotating the wrong kind of credential entirely. Checking which branch
an endpoint belongs to takes a minute; rotating a password that was never the problem costs an
afternoon and, done through the wrong page, produces no change at all.

**A child branch inherits its parent's roles and passwords at the moment it is branched, and does
not track later parent changes.** After resetting a password on a parent, every child still expects
the old one. Reset the role on each branch that will be connected to, and take the connection
string from that branch rather than editing the parent's.

**Rotate Postgres roles under Branch → Roles.** The left-hand *Credentials* page manages S3 and AI
Gateway tokens, not database roles. A reset there will appear to succeed and change nothing.

**Confirm which branch a connection string belongs to, before trusting it.** The endpoint ID is the
first label of the host — `ep-silent-shape-ax7q77lk-pooler.c-4.us-east-2.aws.neon.tech` is endpoint
`ep-silent-shape-ax7q77lk`. Do not infer the branch from the name; check it:

1. **In the Neon console** — open the project, then *Branches*. Each branch lists its compute
   endpoint ID. Match the ID from the connection string against that list. If it appears against no
   branch, the connection string is stale regardless of what the password is.
2. **Get a fresh string from the branch itself** — *Branches → (branch) → Connect*, and copy the
   string shown there rather than editing an old one by hand. Editing an old one is how a host and a
   credential end up from different branches.
3. **If the role is rejected, reset it in the console** — *Branches → (branch) → Roles →
   `neondb_owner` → Reset password*. Neon manages role credentials per branch; a password set by
   `ALTER USER` over SQL is not guaranteed to be what the control plane serves.

**Then prove the databases are distinct before running anything that writes.** Do not rely on row
counts matching or differing — a fresh branch is a copy of its parent, so identical counts prove
nothing. Write to one and read the other:

```sql
-- against the endpoint the local app will use
INSERT INTO contacts (tenant_id, email, first_name, last_name, country, plan, attributes, created_at)
VALUES ('acme', 'isolation-probe@qa.example.com', 'Isolation', 'Probe', 'US', 'pro', '{}'::jsonb, now());

-- against the production endpoint
SELECT count(*) FROM contacts WHERE email = 'isolation-probe@qa.example.com';   -- must be 0

-- then clean up on the first endpoint
DELETE FROM contacts WHERE email = 'isolation-probe@qa.example.com';
```

If that second query returns anything other than `0`, the endpoints are the same database and
`make all` will wipe the demo.

**Until it is proven, set `RESET_DATABASE=false`** in `engage-test-automation/.env`. It costs the
reset-dependent tests and protects everything else.

## Guardrail — built

Implemented rather than suggested, because the report on its own prevents nothing.

`GET /api/health` now returns `database_endpoint` — the `ep-…` label only, never the host, user or
credential: enough to recognise which database this is, useless for reaching it. The suite's
`database_state` fixture calls `looks_like_production()` before every reset and refuses when the
endpoint matches production, or when the API under test is the deployed instance. The refusal names
what it detected, says where the wrong value comes from, and documents the
`ALLOW_PRODUCTION_RESET=true` override.

The endpoint check is the one that matters. The dangerous case — a local application connected to
the production database — is invisible to every other signal: the URL is `127.0.0.1` and health is
green. The hostname check is a fallback for an application too old to report its endpoint.

Seven tests cover the guard itself, including that exact case. Verified end to end as well: armed
against the current endpoint, the suite refuses to start; with the override set, it proceeds.
