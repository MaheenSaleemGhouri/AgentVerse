"""Typed errors, so callers branch on a class rather than on a status code.

The taxonomy mirrors what the API actually distinguishes, because an SDK
that collapses everything into one `APIError` makes the caller re-derive
the difference from `.status_code` — which is the work the SDK exists to
do once.

The distinctions that matter in practice:

- `RateLimited` carries `retry_after`, so a caller can back off correctly
  without parsing a header.
- `ServiceUnavailable` is *not* the same as `RateLimited`, even though
  both mean "try later". The API returns 503 when it cannot check your
  budget — you are not over it — and a client that treated that as a rate
  limit would back off for the wrong reason and log the wrong thing.
- `NotFound` is deliberately what a cross-workspace resource returns.
  The API answers 404 rather than 403 so a workspace's existence is not
  discoverable, and the SDK does not undo that by guessing.
"""

from __future__ import annotations

# ruff: noqa: N818
# `PermissionDenied`, `NotFound`, `Conflict`, `RateLimited` and
# `ServiceUnavailable` deliberately drop the `Error` suffix. They read as
# what the API *said* — `except NotFound:` — which is how every SDK a
# caller already uses names them, and matching that convention matters
# more here than matching PEP 8's suggestion. They all inherit from
# `APIError`, so `except APIError:` still catches them.


class AgentVerseError(Exception):
    """Base class. Catch this to catch everything the SDK raises."""


class ConfigurationError(AgentVerseError):
    """The client was constructed wrongly — missing key, bad base URL.

    Raised at construction rather than on the first request, so a typo in
    deployment configuration fails at startup instead of at 3am on the
    first call.
    """


class APIError(AgentVerseError):
    """The API answered, and the answer was an error."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        code: str | None = None,
        request_id: str | None = None,
        details: object = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        #: Echoed from the response. Quote it in a support conversation
        #: and the exact request can be found in our logs — which is the
        #: entire reason the header exists.
        self.request_id = request_id
        self.details = details
        super().__init__(
            f"{message} (HTTP {status_code}{f', request {request_id}' if request_id else ''})"
        )


class AuthenticationError(APIError):
    """401 — the credential is missing, malformed or revoked."""


class PermissionDenied(APIError):
    """403 — the credential is valid but not allowed to do this.

    Distinct from `NotFound`: a 403 means the resource is in a workspace
    you belong to and you lack the role, and a 404 means you are not
    being told whether it exists at all.
    """


class NotFound(APIError):
    """404 — no such resource, *or* it belongs to another workspace."""


class Conflict(APIError):
    """409 — well-formed, wrong current state.

    A listing already published, a slug already taken, a subscription
    already cancelled. Retrying the identical request will not help;
    reading the current state will.
    """


class ValidationError(APIError):
    """422 — the request shape or contents were rejected.

    `details` carries the API's field-level explanation rather than being
    flattened into the message, because a caller building a form needs
    the structure.
    """


class RateLimited(APIError):
    """429 — over the workspace's or the key's per-minute budget."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 429,
        retry_after: float | None = None,
        code: str | None = None,
        request_id: str | None = None,
        details: object = None,
    ) -> None:
        #: Seconds to wait, from the server. `None` only if the header was
        #: absent, which should not happen — the SDK falls back to its own
        #: backoff in that case rather than retrying immediately.
        self.retry_after = retry_after
        super().__init__(
            message,
            status_code=status_code,
            code=code,
            request_id=request_id,
            details=details,
        )


class ServiceUnavailable(APIError):
    """503 — the platform could not serve this right now.

    Deliberately separate from `RateLimited`. The API returns 503 when it
    cannot check your budget at all, which means you are *not* over it —
    a client that logged this as a rate limit would chase the wrong
    problem.
    """


class ServerError(APIError):
    """5xx other than 503 — our bug, not yours."""


class APIConnectionError(AgentVerseError):
    """The request never got an answer: DNS, TLS, timeout, reset.

    Not an `APIError`, because there is no status code and no request id
    — treating it as one would give callers a status of 0 to branch on.
    """


def error_for_status(
    *,
    status_code: int,
    message: str,
    code: str | None = None,
    request_id: str | None = None,
    details: object = None,
    retry_after: float | None = None,
) -> APIError:
    """Map a status to its class.

    One place, so a caller never has to remember which codes the API uses
    for what — and so adding a distinction later changes one function
    rather than every call site.
    """
    if status_code == 401:
        return AuthenticationError(
            message, status_code=status_code, code=code, request_id=request_id, details=details
        )
    if status_code == 403:
        return PermissionDenied(
            message, status_code=status_code, code=code, request_id=request_id, details=details
        )
    if status_code == 404:
        return NotFound(
            message, status_code=status_code, code=code, request_id=request_id, details=details
        )
    if status_code == 409:
        return Conflict(
            message, status_code=status_code, code=code, request_id=request_id, details=details
        )
    if status_code == 422:
        return ValidationError(
            message, status_code=status_code, code=code, request_id=request_id, details=details
        )
    if status_code == 429:
        return RateLimited(
            message,
            status_code=status_code,
            retry_after=retry_after,
            code=code,
            request_id=request_id,
            details=details,
        )
    if status_code == 503:
        return ServiceUnavailable(
            message, status_code=status_code, code=code, request_id=request_id, details=details
        )
    if status_code >= 500:
        return ServerError(
            message, status_code=status_code, code=code, request_id=request_id, details=details
        )
    return APIError(
        message, status_code=status_code, code=code, request_id=request_id, details=details
    )
