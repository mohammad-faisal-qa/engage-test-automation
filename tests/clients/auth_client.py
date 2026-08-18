"""Login and identity."""

from __future__ import annotations

import httpx

from clients.base import BaseClient
from models import Token, User


class AuthClient(BaseClient):
    """Wraps /api/auth.

    Usable without a token — it is the client that *obtains* them.
    """

    def login(self, email: str, password: str) -> Token:
        """Log in, expecting success. Returns the parsed token."""
        response = self.post(
            "/api/auth/login",
            json={"email": email, "password": password},
            expect=200,
        )
        return Token.model_validate(response.json())

    def login_response(self, email: str, password: str) -> httpx.Response:
        """Log in without expecting anything, for tests about failed logins."""
        return self.post("/api/auth/login", json={"email": email, "password": password})

    def me(self) -> User:
        """The identity behind this client's token."""
        response = self.get("/api/auth/me", expect=200)
        return User.model_validate(response.json())

    def me_response(self) -> httpx.Response:
        return self.get("/api/auth/me")
