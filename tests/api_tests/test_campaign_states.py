"""The campaign status machine.

A campaign moves draft → scheduled → running → sent, and the machine is enforced
by the API rather than by the UI — which is the only place it can be enforced,
since the UI is not the only caller.

The transition worth the most attention is the one that must be *refused*:
draft → sent. It is the shape of every "mark it done" shortcut, and allowing it
would let a campaign report as sent without anything having been sent, leaving
the analytics funnel describing deliveries that do not exist.

Every campaign here is created by the test that uses it, so these assertions
never depend on the seeded campaigns another worker may be driving.
"""

import allure
import pytest

from data.factories import campaign_payload

pytestmark = [pytest.mark.api]


@pytest.fixture
def draft(api):
    """A fresh campaign, which the application always creates as a draft."""
    campaign = api.campaigns().create(campaign_payload())
    assert campaign.status == "draft", (
        f"a new campaign should start as draft, not {campaign.status!r}"
    )
    return campaign


@allure.feature("Campaigns")
@allure.story("A draft can be scheduled")
def test_a_draft_can_be_scheduled(api, draft):
    assert api.campaigns().set_status(draft.id, "scheduled").status == "scheduled"


@allure.feature("Campaigns")
@allure.story("A scheduled campaign can be put back into draft")
def test_a_scheduled_campaign_can_go_back_to_draft(api, draft):
    """Scheduling is reversible, and it should be: noticing a mistake before
    anything is sent is exactly when a campaign ought to be editable again.
    """
    api.campaigns().set_status(draft.id, "scheduled")
    assert api.campaigns().set_status(draft.id, "draft").status == "draft"


@allure.feature("Campaigns")
@allure.story("A campaign runs, then completes")
def test_a_campaign_moves_through_running_to_sent(api, draft):
    campaigns = api.campaigns()
    assert campaigns.set_status(draft.id, "running").status == "running"
    assert campaigns.set_status(draft.id, "sent").status == "sent"


@allure.feature("Campaigns")
@allure.story("A draft cannot jump straight to sent")
def test_a_draft_cannot_jump_straight_to_sent(api, draft):
    """The refusal that matters most.

    Two assertions, and the second is the one with teeth: a 422 that had already
    written the status would look identical from the response alone.
    """
    response = api.campaigns().set_status_response(draft.id, "sent")

    assert response.status_code == 422, (
        f"draft -> sent was accepted with {response.status_code}; a campaign can "
        f"now report as sent without anything having been sent"
    )
    assert api.campaigns().get_one(draft.id).status == "draft", (
        "the transition was refused but the status changed anyway"
    )


@allure.feature("Campaigns")
@allure.story("A sent campaign is terminal")
def test_a_sent_campaign_cannot_be_reopened(api, draft):
    """`sent` is the end. Reopening one would make its delivery history describe
    a campaign that no longer matches it.
    """
    campaigns = api.campaigns()
    campaigns.set_status(draft.id, "running")
    campaigns.set_status(draft.id, "sent")

    for target in ("draft", "scheduled", "running"):
        response = campaigns.set_status_response(draft.id, target)
        assert response.status_code == 422, (
            f"a sent campaign was moved back to {target!r} with "
            f"{response.status_code}"
        )

    assert campaigns.get_one(draft.id).status == "sent"


@allure.feature("Campaigns")
@allure.story("A refused transition names both states")
def test_a_refused_transition_explains_itself(api, draft):
    """The message is part of the contract. "422 Unprocessable Entity" tells the
    caller nothing about which move was refused or what the campaign's state
    actually is, and that is the first thing anyone debugging needs.
    """
    response = api.campaigns().set_status_response(draft.id, "sent")
    detail = str(response.json().get("detail", "")).lower()

    assert "draft" in detail and "sent" in detail, (
        f"the rejection should name the states it refused to move between; "
        f"got {detail!r}"
    )
