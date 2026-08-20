"""Facts about stored data that the HTTP API structurally cannot show.

Three tests, and each one earns its place by the same test: *could an API
response reveal this failure?* Where the answer was yes, the check was dropped
rather than written — the delivery rows themselves, for instance, are returned
in full by `GET /api/campaigns/{id}/deliveries`, so asserting them here would
have duplicated the HTTP layer and rotted on the first schema change.

The rules that constrain this layer, and the honest argument against having it
at all, are in TEST_STRATEGY.md §9.
"""

import pytest

pytestmark = [pytest.mark.db]


# Each entry: the table, and a query that finds rows whose tenant disagrees with
# the tenant of the record they belong to. A correct system returns zero.
#
# Written as joins rather than as "rows I created" on purpose. Any row anywhere
# that fails this is a real defect no matter which test or which worker produced
# it, which makes the assertion both stronger and safe under `-n 4`.
TENANT_STAMP_CHECKS = {
    "deliveries": """
        SELECT count(*) FROM deliveries d
        JOIN campaigns c ON c.id = d.campaign_id
        JOIN contacts  p ON p.id = d.contact_id
        WHERE d.tenant_id <> c.tenant_id OR d.tenant_id <> p.tenant_id
    """,
    "webhook_events": """
        SELECT count(*) FROM webhook_events w
        JOIN deliveries d ON d.id = w.delivery_id
        WHERE w.tenant_id <> d.tenant_id
    """,
    "notification_impressions": """
        SELECT count(*) FROM notification_impressions i
        JOIN onsite_notifications n ON n.id = i.notification_id
        JOIN contacts c ON c.id = i.contact_id
        WHERE i.tenant_id <> n.tenant_id OR i.tenant_id <> c.tenant_id
    """,
}

POPULATION = {name: f"SELECT count(*) FROM {name}" for name in TENANT_STAMP_CHECKS}


@pytest.mark.parametrize("table", sorted(TENANT_STAMP_CHECKS), ids=sorted(TENANT_STAMP_CHECKS))
def test_every_row_carries_the_tenant_of_its_owner(db, stamped_rows, table):
    """The API cannot see this: none of these three tables is reachable over HTTP
    with its `tenant_id` attached.

    `DeliveryOut` has no `tenant_id` field at all, and `webhook_events` and
    `notification_impressions` have no endpoint whatsoever. So a row could be
    written under the wrong tenant and every HTTP test in this suite would still
    pass — the mis-stamped row would simply be invisible until it surfaced as one
    organisation's analytics quietly counting another's sends.

    Tenant isolation is tested over HTTP as a *permission* — acme asks for
    globex's record and is told it does not exist. This is the same promise as a
    *storage* fact: the data was filed under the right owner in the first place.
    A system can pass the first and fail the second, and the failure is the worse
    of the two because nothing reports it.
    """
    assert db.count(POPULATION[table]) > 0, (
        f"{table} is empty, so this assertion proves nothing — the fixture that "
        f"should have created a row through the API did not"
    )

    crossed = db.count(TENANT_STAMP_CHECKS[table])

    assert crossed == 0, (
        f"{crossed} row(s) in {table} carry a tenant_id that disagrees with the "
        f"record they belong to. Data has been filed under the wrong owner, and "
        f"no HTTP response would reveal it because this table's tenant is never "
        f"exposed."
    )


def test_one_idempotency_key_leaves_exactly_one_stored_event(db, stamped_rows, api):
    """The API cannot see this: `webhook_events` has no endpoint.

    Over HTTP a replay is observable — the second call returns `replayed: true`
    and the delivery's `delivered_at` does not move. What HTTP cannot show is
    whether *one row or two* were written. Those are different defects with the
    same symptom: a handler that dedupes on read and a unique constraint that has
    been dropped look identical in sequence, and differ only when two callbacks
    race, which is the one case a sequential test never produces.

    Worth naming while we are here: `POST /api/test/reset` reports counts for
    nine tables and omits `notification_impressions` and `webhook_events` — the
    two that the frequency-cap and idempotency tests silently assume start
    empty. The assumption holds, but nothing over HTTP confirms it, which is
    precisely the kind of silence this layer exists to break.
    """
    key = stamped_rows["idempotency_key"]

    stored = db.count(
        "SELECT count(*) FROM webhook_events WHERE idempotency_key = %s", (key,)
    )
    assert stored == 1, (
        f"idempotency key {key!r} produced {stored} stored event(s), not 1. "
        f"Idempotency means one side effect, and the stored event is the side "
        f"effect — a second row here is a duplicate that HTTP would never show."
    )

    # Replay it, and prove the storage layer still holds one row.
    delivery = api.delivery()
    delivery.receipt(
        stamped_rows["delivery_ids"][0], "delivered", idempotency_key=key
    )

    after = db.count(
        "SELECT count(*) FROM webhook_events WHERE idempotency_key = %s", (key,)
    )
    assert after == 1, (
        f"replaying the same key left {after} stored events. The endpoint "
        f"reported a replay while the database gained a row, which is the exact "
        f"disagreement between handler and storage this test exists to catch."
    )


def test_a_deleted_contact_leaves_no_row_behind(db, api):
    """The API cannot see this: `404` looks identical whether the row is gone or
    merely hidden behind a filter.

    This is not a guard against a hypothetical refactor. It encodes a
    data-retention decision this system has made: **deletion here is physical,
    and personal data does not survive it.** A contact carries an email address
    and a name; when someone asks for that to be removed, "removed" has to mean
    the row is gone, not that a flag now excludes it from queries.

    If that decision ever changes — a `deleted_at` column, an archive table, a
    tombstone — this test fails, and it should. The conversation it forces is the
    point of it. Every HTTP test would keep passing through such a change while
    the data quietly stayed.
    """
    from data.factories import contact_payload

    contacts = api.contacts()
    created = contacts.create(contact_payload())

    assert db.count("SELECT count(*) FROM contacts WHERE id = %s", (created.id,)) == 1, (
        "the contact created through the API is not in the database, so this "
        "test would prove nothing about deleting it"
    )

    contacts.delete_one(created.id)

    remaining = db.count("SELECT count(*) FROM contacts WHERE id = %s", (created.id,))
    assert remaining == 0, (
        f"contact {created.id} still has {remaining} row(s) after a successful "
        f"delete. The API reports it gone and the database has kept it — the "
        f"system is retaining personal data it has told the caller it removed."
    )
