"""The HTTP plumbing every service client sits on.

One place handles the four things that would otherwise be repeated in every
client: attaching the bearer token, logging, attaching request and response to
the Allure report, and turning an unexpected status code into a failure message
that says what happened without needing a debugger.

Why a client layer at all, rather than calling httpx from the tests? Because a
test should read as a statement about behaviour. `contacts.create(payload)` is
a statement; twelve lines of URL building, header assembly and status checking
is not, and it is twelve lines that would then exist in forty tests.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterable

import allure
import httpx

logger = logging.getLogger("tests.http")

# Header values that must never reach a published report.
REDACTED_HEADERS = {"authorization", "x-test-key", "x-webhook-secret"}

# Response bodies are attached in full up to this size; beyond it they are
# truncated, because a 5MB attachment helps nobody read a failure.
MAX_ATTACHMENT_CHARS = 20_000


class TransportFailure(RuntimeError):
    """A request never completed. Not an AssertionError, deliberately: the
    application did not answer, so nothing about its behaviour was observed."""


class UnexpectedStatus(AssertionError):
    """A request returned a status the caller did not expect.

    Subclasses AssertionError so pytest reports it as a failed expectation
    rather than an error in the test framework — the distinction matters when
    reading a CI summary.
    """


def _pretty(payload: Any) -> str:
    try:
        return json.dumps(payload, indent=2, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return str(payload)


def _truncate(text: str) -> str:
    if len(text) <= MAX_ATTACHMENT_CHARS:
        return text
    return f"{text[:MAX_ATTACHMENT_CHARS]}\n... [truncated, {len(text)} chars total]"


# uvicorn closes an idle keep-alive connection after 5 seconds, and httpx's
# default keepalive_expiry is also 5.0 — a dead heat. When a pooled connection
# reaches that age, the client can pick it up in the same instant the server is
# closing it, and the request dies with "connection reset by peer" before it is
# even sent.
#
# It never reproduced locally, where the loop is fast enough that gaps rarely
# reach five seconds. On a contended CI runner with four workers it does, which
# is how a green suite arrived at a red gate.
#
# Expiring client-side at two seconds means this suite never offers the server a
# connection the server might already have given up on. The retries are for the
# genuinely unlucky case — they cover connection establishment only, so no
# request that reached the application is ever sent twice.
# Safe to resend: nothing about them changes state, so a retry can only ever
# repeat a question. Deliberately excludes POST, PATCH and DELETE.
IDEMPOTENT_METHODS = {"GET", "HEAD", "OPTIONS"}
RETRYABLE_ATTEMPTS = 3

SERVER_KEEPALIVE_SECONDS = 5.0
CLIENT_KEEPALIVE_SECONDS = 2.0


def _pooled_transport() -> httpx.HTTPTransport:
    return httpx.HTTPTransport(
        retries=2,
        limits=httpx.Limits(
            max_connections=20,
            max_keepalive_connections=10,
            keepalive_expiry=CLIENT_KEEPALIVE_SECONDS,
        ),
    )


class BaseClient:
    """A thin, honest wrapper over one httpx session."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.default_headers = dict(headers or {})
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=_pooled_transport(),
        )

    # --- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "BaseClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # --- request path ------------------------------------------------------

    def _build_headers(self, override: dict[str, str] | None) -> dict[str, str]:
        headers = dict(self.default_headers)
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        headers.update(override or {})
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        expect: int | Iterable[int] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send one request.

        `expect` is the contract: pass it when a status other than the expected
        one means the test cannot continue, and the client raises a readable
        error. Omit it when the status *is* the thing under test, and assert on
        `response.status_code` yourself.
        """
        response = self._send(method, path, self._build_headers(headers), kwargs)
        self._record(response, kwargs.get("json"))
        if expect is not None:
            self._assert_status(response, expect)
        return response

    def _send(
        self, method: str, path: str, headers: dict[str, str], kwargs: dict
    ) -> httpx.Response:
        """Send one request, retrying only where retrying is provably safe.

        A transport error carries no URL, so "connection reset by peer" in a CI
        summary names neither the call that failed nor the test's intent. Both
        are added here.

        Retries are restricted to methods with no side effects. A POST that
        reached the application and then lost its response looks identical to
        one that never arrived, so resending it could double a delivery — and
        this client posts webhook receipts whose whole point is that they are
        applied once. Reads carry no such risk, and polling is the pattern most
        exposed to a dropped connection.
        """
        attempts = RETRYABLE_ATTEMPTS if method.upper() in IDEMPOTENT_METHODS else 1
        last: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                return self._http.request(method, path, headers=headers, **kwargs)
            except httpx.TransportError as exc:
                last = exc
                logger.warning(
                    "%s %s failed at the transport level (attempt %s/%s): %s",
                    method, path, attempt, attempts, exc,
                )

        raise TransportFailure(
            f"{method} {self.base_url}{path} failed at the transport level after "
            f"{attempts} attempt(s): {type(last).__name__}: {last}\n"
            f"The request never completed, so this is not the application "
            f"refusing it — the connection itself did not survive."
        ) from last

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", path, **kwargs)

    # --- reporting ---------------------------------------------------------

    def _record(self, response: httpx.Response, request_body: Any) -> None:
        """Log the exchange and attach both halves to the Allure report.

        Every request is attached, not only failing ones: when a test fails on
        its third call, the first two are the context you need to understand
        why, and they no longer exist by the time you read the report.
        """
        request = response.request
        safe_headers = {
            name: ("<redacted>" if name.lower() in REDACTED_HEADERS else value)
            for name, value in request.headers.items()
        }

        request_lines = [f"{request.method} {request.url}", "", _pretty(safe_headers)]
        if request_body is not None:
            request_lines += ["", _pretty(request_body)]

        response_body = response.text
        try:
            response_body = _pretty(response.json())
        except ValueError:
            pass

        logger.info(
            "%s %s -> %s (%.0f ms)",
            request.method,
            request.url,
            response.status_code,
            response.elapsed.total_seconds() * 1000 if response.elapsed else 0.0,
        )

        label = f"{request.method} {request.url.path}"
        allure.attach(
            _truncate("\n".join(request_lines)),
            name=f"→ {label}",
            attachment_type=allure.attachment_type.TEXT,
        )
        allure.attach(
            _truncate(f"HTTP {response.status_code}\n\n{response_body}"),
            name=f"← {label} [{response.status_code}]",
            attachment_type=allure.attachment_type.TEXT,
        )

    @staticmethod
    def _assert_status(response: httpx.Response, expect: int | Iterable[int]) -> None:
        allowed = (expect,) if isinstance(expect, int) else tuple(expect)
        if response.status_code in allowed:
            return

        body = response.text
        try:
            body = _pretty(response.json())
        except ValueError:
            pass

        raise UnexpectedStatus(
            f"{response.request.method} {response.request.url}\n"
            f"  expected status: {' or '.join(str(code) for code in allowed)}\n"
            f"  actual status:   {response.status_code}\n"
            f"  response body:   {_truncate(body)}"
        )
