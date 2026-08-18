"""Segments: rule and static lists, plus computed membership."""

from __future__ import annotations

from typing import Any

import httpx

from clients.base import BaseClient
from models import Contact, Segment


class SegmentsClient(BaseClient):
    """Wraps /api/segments.

    `members` is the interesting one: membership is computed on read rather
    than stored, so the same segment can return different contacts as the
    underlying data changes. Tests therefore assert on who is returned, never
    on a stored member list.
    """

    PATH = "/api/segments"

    def list(self) -> list[Segment]:
        response = self.get(self.PATH, expect=200)
        return [Segment.model_validate(row) for row in response.json()]

    def get_one(self, segment_id: int) -> Segment:
        response = self.get(f"{self.PATH}/{segment_id}", expect=200)
        return Segment.model_validate(response.json())

    def get_one_response(self, segment_id: int) -> httpx.Response:
        return self.get(f"{self.PATH}/{segment_id}")

    def members(self, segment_id: int) -> list[Contact]:
        response = self.get(f"{self.PATH}/{segment_id}/members", expect=200)
        return [Contact.model_validate(row) for row in response.json()]

    def members_response(self, segment_id: int) -> httpx.Response:
        return self.get(f"{self.PATH}/{segment_id}/members")

    def create(self, payload: dict[str, Any]) -> Segment:
        response = self.post(self.PATH, json=payload, expect=201)
        return Segment.model_validate(response.json())

    def create_response(self, payload: dict[str, Any]) -> httpx.Response:
        return self.post(self.PATH, json=payload)

    def update(self, segment_id: int, payload: dict[str, Any]) -> Segment:
        response = self.patch(f"{self.PATH}/{segment_id}", json=payload, expect=200)
        return Segment.model_validate(response.json())

    def update_response(self, segment_id: int, payload: dict[str, Any]) -> httpx.Response:
        return self.patch(f"{self.PATH}/{segment_id}", json=payload)

    def delete_one(self, segment_id: int) -> None:
        self.delete(f"{self.PATH}/{segment_id}", expect=204)

    def delete_one_response(self, segment_id: int) -> httpx.Response:
        return self.delete(f"{self.PATH}/{segment_id}")
