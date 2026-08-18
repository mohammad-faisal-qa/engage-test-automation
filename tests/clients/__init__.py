"""Service clients, and the registry that hands them out.

The registry exists because the interesting axis in this application is
*who is asking*: three roles across two tenants is six identities, and every
client needs one. Six named fixtures per client would be forty-eight fixtures
by the end of Phase 2. One `api` fixture with `api.contacts(role="viewer")`
stays readable and grows by one method per new service.

Tokens and clients are both cached for the whole session: logging in is a
bcrypt verification per call, and repeating it several hundred times would make
the suite slower than the application it tests.
"""

from __future__ import annotations

from clients.analytics_client import AnalyticsClient
from clients.auth_client import AuthClient
from clients.base import BaseClient, UnexpectedStatus
from clients.campaigns_client import CampaignsClient
from clients.contacts_client import ContactsClient
from clients.delivery_client import DeliveryClient
from clients.notifications_client import NotificationsClient
from clients.segments_client import SegmentsClient
from clients.surveys_client import SurveysClient

__all__ = [
    "AnalyticsClient",
    "ApiClients",
    "AuthClient",
    "BaseClient",
    "CampaignsClient",
    "ContactsClient",
    "DeliveryClient",
    "NotificationsClient",
    "SegmentsClient",
    "SurveysClient",
    "UnexpectedStatus",
]


class ApiClients:
    """Every service client, for every identity, built once and reused."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float,
        password: str,
        email_for,
        webhook_secret: str = "",
    ) -> None:
        self._base_url = base_url
        self._timeout = timeout
        self._password = password
        self._email_for = email_for
        # Not a bearer token: the delivery webhook is a provider callback, so it
        # is guarded by a shared secret rather than by a login.
        self._webhook_secret = webhook_secret
        self._tokens: dict[tuple[str, str], str] = {}
        self._clients: dict[tuple[type, str | None, str], BaseClient] = {}
        self._open: list[BaseClient] = []

    # --- tokens ------------------------------------------------------------

    def token(self, role: str = "admin", tenant: str = "acme") -> str:
        """A bearer token for one identity, logging in at most once per session."""
        key = (role, tenant)
        if key not in self._tokens:
            with AuthClient(self._base_url, timeout=self._timeout) as anonymous:
                self._tokens[key] = anonymous.login(
                    self._email_for(role, tenant), self._password
                ).access_token
        return self._tokens[key]

    # --- clients -----------------------------------------------------------

    def _client(self, client_type, role: str | None, tenant: str):
        key = (client_type, role, tenant)
        if key not in self._clients:
            token = self.token(role, tenant) if role else None
            client = client_type(self._base_url, token=token, timeout=self._timeout)
            self._clients[key] = client
            self._open.append(client)
        return self._clients[key]

    def auth(self, role: str | None = None, tenant: str = "acme") -> AuthClient:
        """`role=None` gives an unauthenticated client, which is all login needs."""
        return self._client(AuthClient, role, tenant)

    def contacts(self, role: str = "admin", tenant: str = "acme") -> ContactsClient:
        return self._client(ContactsClient, role, tenant)

    def segments(self, role: str = "admin", tenant: str = "acme") -> SegmentsClient:
        return self._client(SegmentsClient, role, tenant)

    def campaigns(self, role: str = "admin", tenant: str = "acme") -> CampaignsClient:
        return self._client(CampaignsClient, role, tenant)

    def delivery(self, role: str = "admin", tenant: str = "acme") -> DeliveryClient:
        client = self._client(DeliveryClient, role, tenant)
        client.webhook_secret = self._webhook_secret
        return client

    def analytics(self, role: str = "admin", tenant: str = "acme") -> AnalyticsClient:
        return self._client(AnalyticsClient, role, tenant)

    def notifications(self, role: str = "admin", tenant: str = "acme") -> NotificationsClient:
        return self._client(NotificationsClient, role, tenant)

    def surveys(self, role: str = "admin", tenant: str = "acme") -> SurveysClient:
        return self._client(SurveysClient, role, tenant)

    def raw(self, role: str = "admin", tenant: str = "acme") -> BaseClient:
        """An authenticated client with no service methods, for paths that have
        no client yet.

        Phase 1 builds auth and contacts clients only, but the seeded facts in
        data/constants.py also cover segments and campaigns. Writing two throwaway
        half-clients now — to be rewritten properly in Phase 2 — would cost more
        than exposing the plumbing for the one test that needs it.
        """
        return self._client(BaseClient, role, tenant)

    # --- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        for client in self._open:
            client.close()
        self._open.clear()
        self._clients.clear()
