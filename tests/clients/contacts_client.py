"""Contacts: the paginated grid plus CRUD."""

from __future__ import annotations

from typing import Any

import httpx

from clients.base import BaseClient
from models import Contact, Page


class ContactsClient(BaseClient):
    """Wraps /api/contacts.

    Two flavours of most methods, and the split is deliberate:

        list()          expects success and returns a parsed model
        list_response() returns the raw response, asserting nothing

    Tests about behaviour use the first and read as prose. Tests about error
    handling use the second, because there the status code *is* the assertion.
    """

    PATH = "/api/contacts"

    # --- reads -------------------------------------------------------------

    def list(
        self,
        *,
        page: int | None = None,
        size: int | None = None,
        q: str | None = None,
        country: str | None = None,
        plan: str | None = None,
    ) -> Page[Contact]:
        response = self.list_response(page=page, size=size, q=q, country=country, plan=plan)
        self._assert_status(response, 200)
        return Page[Contact].model_validate(response.json())

    def list_response(
        self,
        *,
        page: int | None = None,
        size: int | None = None,
        q: str | None = None,
        country: str | None = None,
        plan: str | None = None,
    ) -> httpx.Response:
        # Only send parameters the caller set, so the server's own defaults are
        # what gets exercised when they are omitted.
        params = {
            key: value
            for key, value in {
                "page": page, "size": size, "q": q, "country": country, "plan": plan,
            }.items()
            if value is not None
        }
        return self.get(self.PATH, params=params)

    def get_one(self, contact_id: int) -> Contact:
        response = self.get(f"{self.PATH}/{contact_id}", expect=200)
        return Contact.model_validate(response.json())

    def get_one_response(self, contact_id: int) -> httpx.Response:
        return self.get(f"{self.PATH}/{contact_id}")

    # --- writes ------------------------------------------------------------

    def create(self, payload: dict[str, Any]) -> Contact:
        response = self.post(self.PATH, json=payload, expect=201)
        return Contact.model_validate(response.json())

    def create_response(self, payload: dict[str, Any]) -> httpx.Response:
        return self.post(self.PATH, json=payload)

    def update(self, contact_id: int, payload: dict[str, Any]) -> Contact:
        response = self.patch(f"{self.PATH}/{contact_id}", json=payload, expect=200)
        return Contact.model_validate(response.json())

    def update_response(self, contact_id: int, payload: dict[str, Any]) -> httpx.Response:
        return self.patch(f"{self.PATH}/{contact_id}", json=payload)

    def delete_one(self, contact_id: int) -> None:
        self.delete(f"{self.PATH}/{contact_id}", expect=204)

    def delete_one_response(self, contact_id: int) -> httpx.Response:
        return self.delete(f"{self.PATH}/{contact_id}")
