"""Onsite surveys: question builder, targeting and response capture."""

from __future__ import annotations

from typing import Any

import httpx

from clients.base import BaseClient
from models import Survey


class SurveysClient(BaseClient):
    """Wraps /api/surveys.

    Like impressions, submitting a response is respondent activity rather than
    configuration, so the application does not require the editor role for it —
    a distinction the RBAC tests rely on.
    """

    PATH = "/api/surveys"

    def list(self) -> list[Survey]:
        response = self.get(self.PATH, expect=200)
        return [Survey.model_validate(row) for row in response.json()]

    def get_one(self, survey_id: int) -> Survey:
        response = self.get(f"{self.PATH}/{survey_id}", expect=200)
        return Survey.model_validate(response.json())

    def get_one_response(self, survey_id: int) -> httpx.Response:
        return self.get(f"{self.PATH}/{survey_id}")

    def create(self, payload: dict[str, Any]) -> Survey:
        response = self.post(self.PATH, json=payload, expect=201)
        return Survey.model_validate(response.json())

    def create_response(self, payload: dict[str, Any]) -> httpx.Response:
        return self.post(self.PATH, json=payload)

    def update_response(self, survey_id: int, payload: dict[str, Any]) -> httpx.Response:
        return self.patch(f"{self.PATH}/{survey_id}", json=payload)

    def delete_one_response(self, survey_id: int) -> httpx.Response:
        return self.delete(f"{self.PATH}/{survey_id}")

    def submit_response(self, survey_id: int, payload: dict[str, Any]) -> httpx.Response:
        return self.post(f"{self.PATH}/{survey_id}/responses", json=payload)

    def responses_response(self, survey_id: int) -> httpx.Response:
        return self.get(f"{self.PATH}/{survey_id}/responses")

    def summary(self, survey_id: int) -> dict:
        response = self.get(f"{self.PATH}/{survey_id}/summary", expect=200)
        return response.json()
