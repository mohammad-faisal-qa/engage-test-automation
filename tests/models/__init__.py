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
    # Optional by contract: the application declares a default of {}, so a
    # response may omit it. The contract tests hold both sides to that.
    attributes: dict[str, Any] = {}
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


class Segment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    name: str
    kind: str
    rules: dict[str, Any]
    created_at: datetime


class Campaign(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    name: str
    status: str
    channel: str
    segment_id: int | None = None
    scheduled_at: datetime | None = None
    created_at: datetime


class Delivery(BaseModel):
    """One campaign-to-contact send.

    Every stage carries its own nullable timestamp rather than only a status,
    which is what lets the application survive receipts arriving out of order —
    and what the idempotency and analytics tests assert against.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    contact_id: int
    status: str
    queued_at: datetime
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    opened_at: datetime | None = None
    clicked_at: datetime | None = None
    failed_at: datetime | None = None
    failed_reason: str | None = None


class SendResult(BaseModel):
    """The 202 from a send: an acknowledgement, not an outcome."""

    campaign_id: int
    status: str
    queued: int
    poll: str


class WebhookResult(BaseModel):
    """`applied` says whether this receipt changed anything; `replayed` says
    whether the endpoint recognised the idempotency key and returned the
    original outcome instead of acting again."""

    delivery_id: int
    status: str
    applied: bool
    replayed: bool


class CampaignStats(BaseModel):
    campaign_id: int
    name: str
    status: str
    channel: str
    total: int
    sent: int
    delivered: int
    opened: int
    clicked: int
    failed: int
    delivery_rate: float
    open_rate: float
    click_rate: float


class Notification(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    name: str
    status: str


class Survey(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    name: str
    status: str


__all__ = [
    "Campaign",
    "CampaignStats",
    "Contact",
    "Delivery",
    "Notification",
    "Page",
    "Segment",
    "SendResult",
    "Survey",
    "Token",
    "User",
    "WebhookResult",
]

