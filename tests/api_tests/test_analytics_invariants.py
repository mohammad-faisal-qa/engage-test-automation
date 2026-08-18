"""Analytics, asserted as invariants rather than as numbers.

`sent == 5` is the tempting assertion and the wrong one. It passes today, breaks
the moment the seed changes or another worker sends a campaign, and tells you
nothing about whether the funnel is *correct* — a funnel reporting 5 sent and 9
opened would satisfy it.

What must always hold, for any campaign, at any moment, is the shape:

    clicked <= opened <= delivered <= sent <= total

That is the property the application is actually promising, and it is the one
that catches the real bug in this module. Counts are derived from which stage
timestamps are set rather than from a delivery's current status, precisely so
that a receipt arriving late cannot produce more opens than deliveries.
"""

import allure
import pytest

from data.factories import unique_suffix

pytestmark = [pytest.mark.api]


def key() -> str:
    return f"key-{unique_suffix()}"


def assert_funnel_is_monotonic(stats, context: str) -> None:
    """The one assertion this module exists to make."""
    assert stats.clicked <= stats.opened, (
        f"{context}: clicked ({stats.clicked}) exceeds opened ({stats.opened})"
    )
    assert stats.opened <= stats.delivered, (
        f"{context}: opened ({stats.opened}) exceeds delivered ({stats.delivered})"
    )
    assert stats.delivered <= stats.sent, (
        f"{context}: delivered ({stats.delivered}) exceeds sent ({stats.sent})"
    )
    assert stats.sent <= stats.total, (
        f"{context}: sent ({stats.sent}) exceeds total deliveries ({stats.total})"
    )


@allure.feature("Analytics")
@allure.story("The funnel narrows at every stage")
def test_the_funnel_never_widens_as_it_deepens(api, sent_campaign):
    """Drive a campaign through the funnel and check the shape at each step."""
    campaign, deliveries = sent_campaign
    client = api.delivery()
    analytics = api.analytics()

    assert_funnel_is_monotonic(analytics.campaign(campaign.id), "after send")

    with allure.step("Both deliveries are delivered"):
        for row in deliveries:
            client.receipt(row.id, "delivered", idempotency_key=key())
    assert_funnel_is_monotonic(analytics.campaign(campaign.id), "after delivery")

    with allure.step("One of them is opened"):
        client.receipt(deliveries[0].id, "opened", idempotency_key=key())
    stats = analytics.campaign(campaign.id)
    assert_funnel_is_monotonic(stats, "after one open")

    # A delta this test caused, which is safe to assert on because the campaign
    # is private to it — unlike a global count, nothing else can change it.
    assert stats.opened == 1, f"expected exactly the one open we posted, got {stats.opened}"
    assert stats.clicked == 0


@allure.feature("Analytics")
@allure.story("The funnel holds its shape when receipts arrive out of order")
def test_the_invariant_holds_when_receipts_arrive_out_of_order(api, sent_campaign):
    """The case the whole design exists for.

    A delivery is opened before its `delivered` receipt turns up. If the counts
    were taken from the current status string, this campaign would report one
    open and zero deliveries — a funnel that widens as it deepens, which is
    nonsense a dashboard would render without complaint.
    """
    campaign, deliveries = sent_campaign
    client = api.delivery()

    with allure.step("opened arrives first"):
        client.receipt(deliveries[0].id, "opened", idempotency_key=key())

    stats = api.analytics().campaign(campaign.id)
    assert_funnel_is_monotonic(stats, "opened with no delivered receipt yet")
    assert stats.delivered >= stats.opened, (
        "an open was counted without a delivery — the counts are being taken "
        "from the status string rather than from the stage timestamps"
    )

    with allure.step("the delivered receipt arrives late"):
        client.receipt(deliveries[0].id, "delivered", idempotency_key=key())

    assert_funnel_is_monotonic(
        api.analytics().campaign(campaign.id), "after the late delivered receipt"
    )


@allure.feature("Analytics")
@allure.story("Rates agree with the counts they summarise")
def test_rates_are_consistent_with_the_counts_they_summarise(api, sent_campaign):
    """Two numbers for the same thing can disagree, and a rate is the one people
    quote. The denominators follow marketing convention — delivery rate is of
    sent, open rate is of delivered — so this checks the arithmetic against the
    counts in the same response rather than against anything remembered.
    """
    campaign, deliveries = sent_campaign
    client = api.delivery()

    for row in deliveries:
        client.receipt(row.id, "delivered", idempotency_key=key())
    client.receipt(deliveries[0].id, "opened", idempotency_key=key())

    stats = api.analytics().campaign(campaign.id)

    def expected(numerator: int, denominator: int) -> float:
        return round(numerator / denominator * 100, 1) if denominator else 0.0

    assert stats.delivery_rate == expected(stats.delivered, stats.sent)
    assert stats.open_rate == expected(stats.opened, stats.delivered)
    assert stats.click_rate == expected(stats.clicked, stats.opened)

    # Division by zero has to yield 0.0 rather than an error or a null, because
    # a campaign nobody opened is an ordinary state, not a broken one.
    assert 0.0 <= stats.open_rate <= 100.0


@allure.feature("Analytics")
@allure.story("The overview is internally consistent")
def test_the_overview_totals_agree_with_its_own_campaigns(api, sent_campaign):
    """The overview returns per-campaign stats and tenant totals in one response,
    which is what makes this assertable under parallel execution: both halves
    describe the same instant, so another worker sending a campaign mid-test
    changes both together rather than making them disagree.
    """
    campaign, _deliveries = sent_campaign
    overview = api.analytics().overview()

    campaigns = overview["campaigns"]
    totals = overview["totals"]

    assert any(c["campaign_id"] == campaign.id for c in campaigns), (
        "the campaign this test sent is missing from the tenant overview"
    )

    for entry in campaigns:
        assert entry["clicked"] <= entry["opened"] <= entry["delivered"] <= entry["sent"], (
            f"campaign {entry['campaign_id']} has a funnel that widens: {entry}"
        )

    assert totals["clicked"] <= totals["opened"] <= totals["delivered"] <= totals["sent"], (
        f"the tenant-wide funnel widens: {totals}"
    )

    # Totals cover every delivery in the tenant, including any whose campaign has
    # since been deleted, so they bound the per-campaign sums rather than
    # necessarily equalling them.
    for stage in ("sent", "delivered", "opened", "clicked"):
        assert totals[stage] >= sum(c[stage] for c in campaigns), (
            f"tenant total for {stage} is smaller than the sum of its campaigns"
        )
