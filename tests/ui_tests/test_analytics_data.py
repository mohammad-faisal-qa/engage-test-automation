"""Analytics, asserted against the payload rather than the picture.

A bar chart is a lossy rendering of a number. Asserting that a bar is 240 pixels
wide tests the CSS; it does not test that the number behind it is right, and it
breaks the moment anyone restyles the chart. Worse, the two failure modes are
indistinguishable from the outside: a bar of the wrong length looks exactly like
a bar of the right length for the wrong number.

So these tests intercept the response the page is drawing from, and assert that
what the interface *says* matches what the API *sent*. The chart is then free to
change without breaking anything, and a wrong number fails immediately.

The application helps here: every chart has a table twin, and every stat tile
carries its raw value in a data attribute — so no value is only readable by
measuring something.
"""

import allure
import pytest

from pages.analytics_page import AnalyticsPage

pytestmark = [pytest.mark.ui]


def as_javascript_renders(value: float) -> str:
    """Format a number the way the browser will print it.

    JSON carries these rates as floats, so Python sees 0.0 and 66.7. JavaScript
    has one number type and drops a trailing ".0" when stringifying, so the page
    shows "0%" and "66.7%". Comparing Python's repr against the rendered text
    would fail on every whole-numbered rate — a difference in number formatting
    between two languages, not a defect in either.
    """
    return str(int(value)) if float(value).is_integer() else str(value)


@allure.feature("Analytics")
@allure.story("The stat tiles show the numbers the API returned")
def test_the_stat_tiles_match_the_intercepted_payload(page, settings):
    """Every headline number, checked against the response that produced it."""
    analytics = AnalyticsPage(page, settings)

    with allure.step("Open the dashboard, capturing the overview response"):
        with page.expect_response(AnalyticsPage.OVERVIEW_ENDPOINT) as captured:
            analytics.open_dashboard()
        totals = captured.value.json()["totals"]

    analytics.expect_visible("analytics-totals")

    for name in ("total", "sent", "delivered", "opened", "clicked", "failed"):
        shown = analytics.stat_value(name)
        assert shown == totals[name], (
            f"the {name!r} tile shows {shown}, but the payload behind it said "
            f"{totals[name]}"
        )


@allure.feature("Analytics")
@allure.story("Each campaign's rates match the payload")
def test_campaign_rates_match_the_intercepted_payload(page, settings):
    """The rates are the numbers a person would quote, so they are the ones most
    worth checking against their source. Read as text, never measured.
    """
    analytics = AnalyticsPage(page, settings)

    with page.expect_response(AnalyticsPage.OVERVIEW_ENDPOINT) as captured:
        analytics.open_dashboard()
    campaigns = captured.value.json()["campaigns"]

    assert campaigns, "the seeded tenant should have campaigns to report on"

    for campaign in campaigns:
        card_rates = analytics.rates_text(campaign["campaign_id"])
        for key, label in (
            ("delivery_rate", "delivered"),
            ("open_rate", "opened"),
            ("click_rate", "clicked"),
        ):
            expected = f"{as_javascript_renders(campaign[key])}% {label}"
            assert expected in card_rates, (
                f"campaign {campaign['campaign_id']} card reads {card_rates!r}, "
                f"which does not contain {expected!r} from the payload"
            )


@allure.feature("Analytics")
@allure.story("The table twin carries the same numbers as the charts")
def test_the_table_view_matches_the_intercepted_payload(page, settings):
    """The accessible view of the same data.

    Two renderings of one payload are two chances to disagree, and the table is
    the one someone using a screen reader gets — so it is the one that must not
    quietly drift.
    """
    analytics = AnalyticsPage(page, settings)

    with page.expect_response(AnalyticsPage.OVERVIEW_ENDPOINT) as captured:
        analytics.open_table_view()
    campaigns = captured.value.json()["campaigns"]

    analytics.expect_visible("analytics-table")
    rows = analytics.testid("analytics-table").locator("tbody tr")
    analytics.expect_count(rows, len(campaigns))

    for index, campaign in enumerate(campaigns):
        cells = rows.nth(index).locator("td").all_inner_texts()
        assert cells[0] == str(campaign["campaign_id"])
        assert cells[1] == campaign["name"]
        assert cells[2] == campaign["status"]
        # Counts, in the order the header declares them.
        assert cells[4:10] == [
            str(campaign[key])
            for key in ("total", "sent", "delivered", "opened", "clicked", "failed")
        ], f"row {index} counts disagree with the payload: {cells}"

        # The three rate columns, formatted as the browser prints them.
        assert cells[10:13] == [
            f"{as_javascript_renders(campaign[key])}%"
            for key in ("delivery_rate", "open_rate", "click_rate")
        ], f"row {index} rates disagree with the payload: {cells}"
