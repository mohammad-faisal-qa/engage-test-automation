# DEF-001 — Deleting a contact that has deliveries returns 500

| | |
|---|---|
| **Component** | engage-app · `api/app/routers/contacts.py` |
| **Severity** | **High** — raised from Medium: the same unhandled error also destabilises CI, see [DEF-004](DEF-004-ci-only-connection-reset.md) |
| **Priority** | **High** — three CI runs were lost to it before the cause was identified |
| **Status** | Open — reported, not fixed (the application is a separate repository) |
| **Found** | 2026-08-18, during Phase 6 CI triage |
| **Found by** | Postgres constraint errors in the CI service-container log, then reproduced directly |

## Summary

`DELETE /api/contacts/{id}` returns **500 Internal Server Error** with the body
`Internal Server Error` when the contact has delivery records. The delete is correctly refused —
the database's foreign key holds — but the failure surfaces as a server error rather than as the
conflict it is.

## Impact

An administrator removing a contact who has ever been sent a campaign sees a generic server error.
Three consequences, in order of how much they cost:

1. **The caller cannot tell a bug from a rule.** "Internal Server Error" gives no indication that the
   contact is referenced by deliveries, so the obvious next step is to retry, then to report an
   outage.
2. **It is indistinguishable from a real fault.** A genuine 500 in this endpoint would look exactly
   the same, so monitoring cannot separate "someone tried to delete a referenced contact" from "the
   database is down".
3. **It pollutes error budgets and logs.** Each attempt writes a Postgres `ERROR` line and an
   unhandled-exception traceback for what is, in fact, correct behaviour.

Data is never at risk: the contact and its deliveries are intact afterwards.

**A fourth consequence, found later and worse than the other three.** Under a high request rate the
unhandled exception does not reliably produce a 500 at all — the connection is reset mid-response.
That turned this from a cosmetic error-handling gap into three lost CI runs and a day of misdirected
investigation, because the symptom appeared in a completely different place: fixture teardown for
the delivery tests. See [DEF-004](DEF-004-ci-only-connection-reset.md).

## Environment

Reproduced against `engage-app` at `9e0645e`, Python 3.14, Postgres 18 (Neon) and Postgres 16 (CI
service container). Behaviour identical on both.

## Steps to reproduce

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@acme.example.com","password":"Password123!"}' | jq -r .access_token)

# Contact 1 has seeded deliveries.
curl -s -o /dev/null -w '%{http_code}\n' -X DELETE localhost:8000/api/contacts/1 \
  -H "Authorization: Bearer $TOKEN"
```

## Expected vs actual

| | |
|---|---|
| **Expected** | `409 Conflict`, with a body explaining that the contact has deliveries and cannot be removed |
| **Actual** | `500 Internal Server Error`, body `Internal Server Error` |
| **Verified after** | `GET /api/contacts/1` → `200`; the contact is untouched |

## Root cause

`create_contact` and `update_contact` both wrap their `db.commit()` in
`try/except IntegrityError` and translate it into a `409`. `delete_contact` does not:

```python
@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(...):
    contact = _get_owned(contact_id, db, user)
    db.delete(contact)
    db.commit()          # <- deliveries_contact_id_fkey raises here, unhandled
```

The pattern was applied to the two endpoints where a duplicate email was anticipated, and not to the
one where a *reference* is the constraint that bites. The handler is a three-line addition.

## Why testing missed it

Two reasons, and the second is the more interesting.

**The API tests only ever delete contacts they created**, none of which have deliveries — the
deletion tests use fresh contacts, and the delivery tests use a private cohort they do not clean up
through this path. The referenced-contact case was never constructed on purpose.

**It was visible for weeks in test output and nobody read it.** The cohort fixtures call
`delete_one_response()` as best-effort cleanup, so every run that sent a campaign produced these
500s and discarded them. The failure was in front of us on every run, in a response we had
deliberately decided not to assert on. *Best-effort cleanup is a place where defects go to hide.*

It surfaced only because CI prints the Postgres container log, where the constraint violations were
too repetitive to ignore — and even then it was filed as cosmetic. Its real cost was only understood
once the transport errors in DEF-004 were made to name the request that caused them.

## Suggested fix

Mirror the existing pattern:

```python
try:
    db.commit()
except IntegrityError:
    db.rollback()
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="This contact has deliveries and cannot be removed",
    )
```

## Test to add once fixed

`test_a_contact_with_deliveries_cannot_be_deleted` — send a campaign to a private cohort, attempt to
delete a contact in it, assert `409` and that the contact still exists. Currently absent by
omission, not by decision.
