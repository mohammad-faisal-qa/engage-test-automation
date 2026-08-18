"""Campaign sending and the provider webhook.

This is the client that has to cope with the two awkward parts of the
application, and both are deliberate on the app's side:

* **Sending is asynchronous.** `POST /send` returns 202 with nothing useful in
  the body; the deliveries reach `sent` a moment later. So this client offers
  `wait_until_sent`, which polls. There is no sleep anywhere in it.
* **Webhooks repeat.** The endpoint is idempotent by header key, so the client
  makes the key an explicit argument rather than generating one silently —
  posting "the same" event twice is the whole point of the idempotency tests,
  and that only means something if the caller controls the key.
"""

from __future__ import annotations

import httpx

from clients.base import BaseClient
from models import Delivery, SendResult, WebhookResult
from utils.waits import poll_until


class DeliveryClient(BaseClient):
    """Wraps /api/campaigns/{id}/send, /deliveries and /api/webhooks/delivery."""

    # Set by the client registry: the webhook is not JWT-authenticated, because
    # it is a callback from a sending provider rather than a user action. It is
    # guarded by a shared secret instead.
    webhook_secret: str = ""

    # --- sending -----------------------------------------------------------

    def send(self, campaign_id: int) -> SendResult:
        response = self.post(f"/api/campaigns/{campaign_id}/send", expect=202)
        return SendResult.model_validate(response.json())

    def send_response(self, campaign_id: int) -> httpx.Response:
        return self.post(f"/api/campaigns/{campaign_id}/send")

    def deliveries(self, campaign_id: int) -> list[Delivery]:
        response = self.deliveries_response(campaign_id)
        self._assert_status(response, 200)
        return [Delivery.model_validate(row) for row in response.json()]

    def deliveries_response(self, campaign_id: int) -> httpx.Response:
        return self.get(f"/api/campaigns/{campaign_id}/deliveries")

    def wait_until_sent(
        self,
        campaign_id: int,
        *,
        timeout: float = 30.0,
        interval: float = 0.25,
    ) -> list[Delivery]:
        """Poll until no delivery is still queued, then return them all.

        The condition is "nothing is queued any more" rather than "everything
        says sent", because a delivery that failed is also finished — waiting
        for it to say `sent` would hang until the timeout on a system that had
        already given its answer.
        """

        def finished() -> list[Delivery] | None:
            rows = self.deliveries(campaign_id)
            if rows and all(row.status != "queued" for row in rows):
                return rows
            return None

        return poll_until(
            finished,
            timeout=timeout,
            interval=interval,
            message=(
                f"campaign {campaign_id} still had queued deliveries after the "
                f"send should have completed"
            ),
        )

    # --- receipts ----------------------------------------------------------

    def receipt_response(
        self,
        delivery_id: int,
        event: str,
        *,
        idempotency_key: str,
        reason: str | None = None,
        secret: str | None = None,
    ) -> httpx.Response:
        """Post one delivery receipt, asserting nothing.

        `secret=None` sends the configured one; pass a value to test rejection,
        and pass an empty string to omit the header entirely.
        """
        headers: dict[str, str] = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        chosen = self.webhook_secret if secret is None else secret
        if chosen:
            headers["X-Webhook-Secret"] = chosen

        body: dict[str, object] = {"delivery_id": delivery_id, "event": event}
        if reason is not None:
            body["reason"] = reason

        return self.post("/api/webhooks/delivery", json=body, headers=headers)

    def receipt(
        self,
        delivery_id: int,
        event: str,
        *,
        idempotency_key: str,
        reason: str | None = None,
    ) -> WebhookResult:
        response = self.receipt_response(
            delivery_id, event, idempotency_key=idempotency_key, reason=reason
        )
        self._assert_status(response, 200)
        return WebhookResult.model_validate(response.json())
