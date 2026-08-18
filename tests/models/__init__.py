"""Pydantic models for the responses the tests consume.

These are deliberately *the tests' own* models, not imports from the
application — which the repository split now enforces rather than merely asks
for, since `engage-app` is not importable from here at all.
Importing the application's schemas would make the tests agree with the
application by construction: a field renamed in both places at once would still
pass. Restating the shape here means the suite fails when the contract moves.

They are also deliberately tolerant of unknown fields. Adding a field to a
response is backwards-compatible and should not fail a functional test; proving
the *whole* published contract is the job of the OpenAPI contract tests in
Phase 3. Two layers, two different questions:

    these models     "is what I depend on present and the right type?"
    contract tests   "does the response match everything the app promises?"
"""

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

ItemT = TypeVar("ItemT")


class Token(BaseModel):
    access_token: str
    token_type: str


class User(BaseModel):
    """The identity behind a token, as returned by GET /api/auth/me."""

    id: int
    tenant_id: str
    email: str
    name: str
    role: str


class Contact(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    email: str
    first_name: str
    last_name: str
    country: str
    plan: str
    attributes: dict[str, Any]
    created_at: datetime


class Page(BaseModel, Generic[ItemT]):
    """The envelope every list endpoint returns."""

    items: list[ItemT]
    total: int
    page: int
    size: int

    @property
    def ids(self) -> list[int]:
        """Ids of the items on this page, for overlap and ordering assertions."""
        return [item.id for item in self.items]  # type: ignore[attr-defined]


__all__ = ["Contact", "Page", "Token", "User"]
