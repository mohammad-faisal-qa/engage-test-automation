"""Campaigns: CRUD over a guarded status machine."""

from __future__ import annotations

from typing import Any

import httpx

from clients.base import BaseClient
from models import Campaign


class CampaignsClient(BaseClient):
    """Wraps /api/campaigns.

    `set_status` exists as its own method because the status machine is the
    thing worth testing here, and a test that reads
    `campaigns.set_status_response(id, "sent")` says what it means far better
    than a PATCH with a dict literal.
    """

    PATH = "/api/campaigns"

    def list(self) -> list[Campaign]:
        response = self.get(self.PATH, expect=200)
        return [Campaign.model_validate(row) for row in response.json()]

    def get_one(self, campaign_id: int) -> Campaign:
        response = self.get(f"{self.PATH}/{campaign_id}", expect=200)
        return Campaign.model_validate(response.json())

    def get_one_response(self, campaign_id: int) -> httpx.Response:
        return self.get(f"{self.PATH}/{campaign_id}")

    def create(self, payload: dict[str, Any]) -> Campaign:
        response = self.post(self.PATH, json=payload, expect=201)
        return Campaign.model_validate(response.json())

    def create_response(self, payload: dict[str, Any]) -> httpx.Response:
        return self.post(self.PATH, json=payload)

    def update(self, campaign_id: int, payload: dict[str, Any]) -> Campaign:
        response = self.patch(f"{self.PATH}/{campaign_id}", json=payload, expect=200)
        return Campaign.model_validate(response.json())

    def update_response(self, campaign_id: int, payload: dict[str, Any]) -> httpx.Response:
        return self.patch(f"{self.PATH}/{campaign_id}", json=payload)

    def set_status(self, campaign_id: int, status: str) -> Campaign:
        return self.update(campaign_id, {"status": status})

    def set_status_response(self, campaign_id: int, status: str) -> httpx.Response:
        return self.update_response(campaign_id, {"status": status})

    def delete_one(self, campaign_id: int) -> None:
        self.delete(f"{self.PATH}/{campaign_id}", expect=204)

    def delete_one_response(self, campaign_id: int) -> httpx.Response:
        return self.delete(f"{self.PATH}/{campaign_id}")
