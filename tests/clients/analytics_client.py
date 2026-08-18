"""Campaign analytics — the numbers behind a dashboard chart."""

from __future__ import annotations

import httpx

from clients.base import BaseClient
from models import CampaignStats


class AnalyticsClient(BaseClient):
    """Wraps /api/analytics.

    The counts here are derived from which stage timestamps are set rather than
    from a delivery's current status, which is what makes the funnel monotonic
    even when receipts arrive out of order. The tests assert that invariant
    rather than any fixed number.
    """

    PATH = "/api/analytics"

    def campaign(self, campaign_id: int) -> CampaignStats:
        response = self.get(f"{self.PATH}/campaigns/{campaign_id}", expect=200)
        return CampaignStats.model_validate(response.json())

    def campaign_response(self, campaign_id: int) -> httpx.Response:
        return self.get(f"{self.PATH}/campaigns/{campaign_id}")

    def overview(self) -> dict:
        response = self.get(f"{self.PATH}/overview", expect=200)
        return response.json()

    def overview_response(self) -> httpx.Response:
        return self.get(f"{self.PATH}/overview")
