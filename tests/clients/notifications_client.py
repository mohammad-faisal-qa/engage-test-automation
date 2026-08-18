"""Onsite notifications: trigger rules, display rules and frequency capping."""

from __future__ import annotations

from typing import Any

import httpx

from clients.base import BaseClient
from models import Notification


class NotificationsClient(BaseClient):
    """Wraps /api/notifications.

    `eligibility` evaluates the whole rule chain for one contact and is the
    endpoint the frequency-cap journeys in Phase 6 are built on. Recording an
    impression is deliberately not editor-gated by the application: being shown
    a notification is runtime telemetry, not a configuration change.
    """

    PATH = "/api/notifications"

    def list(self) -> list[Notification]:
        response = self.get(self.PATH, expect=200)
        return [Notification.model_validate(row) for row in response.json()]

    def get_one(self, notification_id: int) -> Notification:
        response = self.get(f"{self.PATH}/{notification_id}", expect=200)
        return Notification.model_validate(response.json())

    def get_one_response(self, notification_id: int) -> httpx.Response:
        return self.get(f"{self.PATH}/{notification_id}")

    def create(self, payload: dict[str, Any]) -> Notification:
        response = self.post(self.PATH, json=payload, expect=201)
        return Notification.model_validate(response.json())

    def create_response(self, payload: dict[str, Any]) -> httpx.Response:
        return self.post(self.PATH, json=payload)

    def update_response(self, notification_id: int, payload: dict[str, Any]) -> httpx.Response:
        return self.patch(f"{self.PATH}/{notification_id}", json=payload)

    def delete_one_response(self, notification_id: int) -> httpx.Response:
        return self.delete(f"{self.PATH}/{notification_id}")

    def record_impression_response(
        self, notification_id: int, contact_id: int
    ) -> httpx.Response:
        return self.post(
            f"{self.PATH}/{notification_id}/impressions",
            params={"contact_id": contact_id},
        )

    def eligibility(self, notification_id: int, contact_id: int) -> dict:
        response = self.eligibility_response(notification_id, contact_id)
        self._assert_status(response, 200)
        return response.json()

    def eligibility_response(self, notification_id: int, contact_id: int) -> httpx.Response:
        return self.get(
            f"{self.PATH}/{notification_id}/eligibility",
            params={"contact_id": contact_id},
        )
