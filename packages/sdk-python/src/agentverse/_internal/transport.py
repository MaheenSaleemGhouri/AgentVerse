"""The one place that speaks HTTP.

Every resource method goes through `request`, so authentication, retry,
error mapping and the request id appear once rather than in each of them.

**Errors are read from the body, not guessed from the status.** The API
returns a stable `code` in a fixed envelope, and callers branch on it —
so the transport pulls out `code`, `message` and `details` and hands them
to the typed exception rather than stringifying whatever came back.

**`request_id` is always attached.** It is on every response and it is
the only thing that makes a support conversation about one failed call
tractable. An SDK that drops it forces the customer to describe their
problem in prose.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from agentverse._internal.retry import decide, parse_retry_after
from agentverse.errors import APIConnectionError, APIError, error_for_status

USER_AGENT = "agentverse-python/0.1.0a0"
REQUEST_ID_HEADER = "X-Request-ID"


def _extract_error(response: httpx.Response) -> tuple[str, str | None, object]:
    """`(message, code, details)` from the API's error envelope.

    Falls back to the raw text when the body is not the envelope — an
    error from a proxy in front of the API is still an error the caller
    needs to see, and swallowing it because it had the wrong shape would
    turn "502 from the load balancer" into "unknown error".
    """
    try:
        body = response.json()
    except ValueError:
        return (response.text or f"HTTP {response.status_code}"), None, None

    if isinstance(body, dict):
        detail = body.get("detail", body.get("error"))
        if isinstance(detail, dict):
            return (
                str(detail.get("message", detail.get("code", "Request failed"))),
                detail.get("code"),
                detail,
            )
        if isinstance(detail, str):
            return detail, None, None
        if isinstance(detail, list):
            # FastAPI's validation-error shape. Kept structured: a caller
            # building a form needs to know which field failed.
            return "Request validation failed", "validation_error", detail
    return f"HTTP {response.status_code}", None, body


def _raise_for_response(response: httpx.Response) -> None:
    message, code, details = _extract_error(response)
    raise error_for_status(
        status_code=response.status_code,
        message=message,
        code=code,
        request_id=response.headers.get(REQUEST_ID_HEADER),
        details=details,
        retry_after=parse_retry_after(response.headers.get("Retry-After")),
    )


class Transport:
    """Shared request logic for the sync and async clients.

    Holds no client of its own: both clients own their httpx instance and
    lifecycle, and this only decides what to send and what to do with
    what came back.
    """

    def __init__(self, *, base_url: str, api_key: str, max_retries: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.max_retries = max_retries

    def headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def should_retry(
        self,
        *,
        method: str,
        attempt: int,
        status_code: int | None,
        retry_after: float | None,
        idempotency_key: str | None,
        connection_failed: bool,
    ) -> tuple[bool, float]:
        decision = decide(
            method=method,
            attempt=attempt,
            max_retries=self.max_retries,
            status_code=status_code,
            retry_after=retry_after,
            has_idempotency_key=idempotency_key is not None,
            connection_failed=connection_failed,
        )
        return decision.retry, decision.delay_seconds


def _prepare(
    transport: Transport,
    *,
    method: str,
    path: str,
    idempotency_key: str | None,
    extra_headers: dict[str, str] | None,
) -> tuple[str, dict[str, str]]:
    headers = dict(extra_headers or {})
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return f"{transport.base_url}{path}", transport.headers(headers)


def send_sync(
    client: httpx.Client,
    transport: Transport,
    *,
    method: str,
    path: str,
    json_body: Any = None,
    params: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    url, headers = _prepare(
        transport,
        method=method,
        path=path,
        idempotency_key=idempotency_key,
        extra_headers=extra_headers,
    )
    attempt = 0
    while True:
        try:
            response = client.request(method, url, json=json_body, params=params, headers=headers)
        except httpx.HTTPError as exc:
            retry, delay = transport.should_retry(
                method=method,
                attempt=attempt,
                status_code=None,
                retry_after=None,
                idempotency_key=idempotency_key,
                connection_failed=True,
            )
            if not retry:
                raise APIConnectionError(str(exc)) from exc
            time.sleep(delay)
            attempt += 1
            continue

        if response.is_success:
            return _decode(response)

        retry, delay = transport.should_retry(
            method=method,
            attempt=attempt,
            status_code=response.status_code,
            retry_after=parse_retry_after(response.headers.get("Retry-After")),
            idempotency_key=idempotency_key,
            connection_failed=False,
        )
        if not retry:
            _raise_for_response(response)
        time.sleep(delay)
        attempt += 1


async def send_async(
    client: httpx.AsyncClient,
    transport: Transport,
    *,
    method: str,
    path: str,
    json_body: Any = None,
    params: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    url, headers = _prepare(
        transport,
        method=method,
        path=path,
        idempotency_key=idempotency_key,
        extra_headers=extra_headers,
    )
    attempt = 0
    while True:
        try:
            response = await client.request(
                method, url, json=json_body, params=params, headers=headers
            )
        except httpx.HTTPError as exc:
            retry, delay = transport.should_retry(
                method=method,
                attempt=attempt,
                status_code=None,
                retry_after=None,
                idempotency_key=idempotency_key,
                connection_failed=True,
            )
            if not retry:
                raise APIConnectionError(str(exc)) from exc
            await asyncio.sleep(delay)
            attempt += 1
            continue

        if response.is_success:
            return _decode(response)

        retry, delay = transport.should_retry(
            method=method,
            attempt=attempt,
            status_code=response.status_code,
            retry_after=parse_retry_after(response.headers.get("Retry-After")),
            idempotency_key=idempotency_key,
            connection_failed=False,
        )
        if not retry:
            _raise_for_response(response)
        await asyncio.sleep(delay)
        attempt += 1


def _decode(response: httpx.Response) -> Any:
    """`None` for 204, parsed JSON otherwise.

    A 204 has no body by definition; calling `.json()` on it raises, and
    an SDK that let that escape would turn every successful delete into
    an exception.
    """
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise APIError(
            "The API returned a success status with a body that is not JSON",
            status_code=response.status_code,
            request_id=response.headers.get(REQUEST_ID_HEADER),
        ) from exc
