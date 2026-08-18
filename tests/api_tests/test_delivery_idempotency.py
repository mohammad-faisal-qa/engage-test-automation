"""Asynchronous sending, and receipts that repeat or arrive out of order.

Both behaviours here are ones real integrations have to survive, and both are
invisible to a test that only checks status codes.

A provider retries a callback whenever it is unsure the first one landed, so the
same receipt arrives more than once. The endpoint is idempotent by header key,
and "idempotent" has to mean *one side effect*, not merely *a second 200*. Every
test below therefore asserts on the delivery row, not on the response alone.

Receipts also arrive out of order — an `opened` can overtake the `delivered`
that logically preceded it. Stage timestamps are independent and the status only
moves forward, so a late receipt cannot walk the funnel backwards.

Nothing here sleeps. The send is asynchronous, so it is polled to completion.
"""

import allure
import pytest

from data.factories import unique_suffix

pytestmark = [pytest.mark.api]


def key() -> str:
    """A fresh idempotency key. Unique per call, so reuse is always deliberate."""
    return f"key-{unique_suffix()}"


@allure.feature("Delivery")
@allure.story("The same receipt posted twice has exactly one effect")
def test_the_same_receipt_posted_twice_has_exactly_one_effect(api, sent_campaign):
    """Post the identical payload twice under one key, then look at the row.

    The second response being 200 proves nothing on its own — an endpoint that
    applied the event twice would also return 200. What proves it is
    `delivered_at` being the same instant afterwards as it was before.
    """
    campaign, deliveries = sent_campaign
    delivery = deliveries[0]
    shared_key = key()
    client = api.delivery()

    with allure.step("First receipt"):
        first = client.receipt(delivery.id, "delivered", idempotency_key=shared_key)
    assert first.applied is True, "the first receipt should have changed something"
    assert first.replayed is False

    after_first = next(
        row for row in client.deliveries(campaign.id) if row.id == delivery.id
    )
    assert after_first.delivered_at is not None

    with allure.step("The identical receipt again, under the same key"):
        second = client.receipt(delivery.id, "delivered", idempotency_key=shared_key)
    assert second.replayed is True, (
        "the endpoint did not recognise the repeated idempotency key, so the "
        "event was processed a second time"
    )

    after_second = next(
        row for row in client.deliveries(campaign.id) if row.id == delivery.id
    )
    assert after_second.delivered_at == after_first.delivered_at, (
        "delivered_at moved, so the duplicate receipt was applied a second time"
    )
    assert after_second.status == after_first.status


@allure.feature("Delivery")
@allure.story("A repeat under a new key is still applied only once")
def test_the_same_event_under_a_new_key_is_not_applied_twice(api, sent_campaign):
    """Two defences, and this test separates them.

    The idempotency key catches a provider retrying. But a provider that
    generates a fresh key for a genuinely duplicate event slips past that, so
    the state machine has to be idempotent too: a stage timestamp is written
    once and never overwritten. Here `replayed` is false — the key was new — and
    `applied` must still be false, because nothing was left to change.
    """
    campaign, deliveries = sent_campaign
    delivery = deliveries[0]
    client = api.delivery()

    first = client.receipt(delivery.id, "delivered", idempotency_key=key())
    assert first.applied is True

    second = client.receipt(delivery.id, "delivered", idempotency_key=key())
    assert second.replayed is False, "a fresh key should not be treated as a replay"
    assert second.applied is False, (
        "a second delivered event changed the row again, so stage timestamps "
        "are being overwritten rather than set once"
    )


@allure.feature("Delivery")
@allure.story("Late receipts do not walk the funnel backwards")
def test_receipts_arriving_out_of_order_do_not_regress_the_status(api, sent_campaign):
    """`opened` first, then the `delivered` that logically preceded it.

    The naive implementation assigns status from whichever receipt arrived last,
    which would leave this delivery reading `delivered` after it had already been
    opened — and the analytics funnel would then report more opens than
    deliveries.
    """
    campaign, deliveries = sent_campaign
    delivery = deliveries[0]
    client = api.delivery()

    with allure.step("The opened receipt overtakes the delivered one"):
        client.receipt(delivery.id, "opened", idempotency_key=key())
    with allure.step("The delivered receipt arrives late"):
        client.receipt(delivery.id, "delivered", idempotency_key=key())

    row = next(r for r in client.deliveries(campaign.id) if r.id == delivery.id)

    assert row.opened_at is not None
    assert row.delivered_at is not None, (
        "the late delivered receipt was discarded; its timestamp should be "
        "recorded even though it arrived after the open"
    )
    assert row.status == "opened", (
        f"status regressed to {row.status!r} when the late delivered receipt "
        f"arrived — the funnel can now report more opens than deliveries"
    )


@allure.feature("Delivery")
@allure.story("An asynchronous send completes when polled")
def test_an_asynchronous_send_completes_when_polled(api, sent_campaign):
    """The endpoint returns 202 before the work is done, so the only honest
    assertion is one made after polling. The fixture does the polling; this
    checks the state it polled to.
    """
    campaign, deliveries = sent_campaign

    assert deliveries, "the send produced no deliveries"
    for row in deliveries:
        assert row.status != "queued", f"delivery {row.id} was still queued"
        assert row.sent_at is not None, f"delivery {row.id} has no sent_at"

    assert api.campaigns().get_one(campaign.id).status == "sent", (
        "every delivery finished but the campaign was not moved to sent"
    )


@allure.feature("Delivery")
@allure.story("A receipt without an idempotency key is refused")
def test_a_receipt_without_an_idempotency_key_is_rejected(api, sent_campaign):
    """Refusing the request is the right call: without a key the endpoint cannot
    recognise a retry, so accepting it would silently give up the guarantee.
    """
    _campaign, deliveries = sent_campaign

    response = api.delivery().receipt_response(
        deliveries[0].id, "delivered", idempotency_key=""
    )

    assert response.status_code == 400, (
        "a receipt with no Idempotency-Key was accepted, so duplicate delivery "
        "of it could not be detected"
    )


@allure.feature("Delivery")
@allure.story("A receipt with the wrong secret is refused")
def test_a_receipt_with_the_wrong_secret_is_rejected(api, sent_campaign):
    """The webhook is not JWT-authenticated — it is a provider callback — so the
    shared secret is the only thing standing between a public URL and anyone
    fabricating delivery events on the demo.
    """
    _campaign, deliveries = sent_campaign
    delivery = deliveries[0]

    response = api.delivery().receipt_response(
        delivery.id, "delivered", idempotency_key=key(), secret="not-the-secret"
    )
    assert response.status_code == 401

    row = next(r for r in api.delivery().deliveries(_campaign.id) if r.id == delivery.id)
    assert row.delivered_at is None, (
        "the receipt was rejected with 401 but applied anyway"
    )


@allure.feature("Delivery")
@allure.story("A receipt for an unknown delivery is not found")
def test_a_receipt_for_an_unknown_delivery_is_not_found(api, sent_campaign):
    _campaign, deliveries = sent_campaign
    unknown = max(row.id for row in deliveries) + 10_000_000

    response = api.delivery().receipt_response(
        unknown, "delivered", idempotency_key=key()
    )

    assert response.status_code == 404


@allure.feature("Delivery")
@allure.story("A failed receipt records why")
def test_a_failed_receipt_records_its_reason(api, sent_campaign):
    """A failure needs its reason kept, because "why did this not arrive" is the
    question anyone actually asks, and the status alone cannot answer it.
    """
    campaign, deliveries = sent_campaign
    delivery = deliveries[0]

    result = api.delivery().receipt(
        delivery.id, "failed", idempotency_key=key(), reason="mailbox_full"
    )
    assert result.status == "failed"

    row = next(r for r in api.delivery().deliveries(campaign.id) if r.id == delivery.id)
    assert row.failed_at is not None
    assert row.failed_reason == "mailbox_full"
