"""AgentVerse's internal provider-error taxonomy (CLAUDE.md §9 Provider
abstraction: "Provider-specific errors ... are translated to AgentVerse's
internal error taxonomy at the boundary"). `infrastructure/providers/`
is the only place that ever catches an OpenAI SDK exception — everywhere
else in this codebase only ever sees one of these.

Every subclass carries a stable, additive `code` string. These codes are
mirrored (never generated) in `packages/contracts/src/provider-error-
taxonomy.ts` so the frontend can render provider failures without ever
importing a Python type or an OpenAI SDK error class.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base for every provider-boundary error. Never raised directly."""

    code: str = "provider_error"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ProviderRateLimitError(ProviderError):
    """The provider is rate-limiting this key/org right now.

    `retry_after_seconds` is the provider's own hint when it supplies
    one (e.g. a `Retry-After` header); the adapter's bounded backoff
    uses it as a floor, never as a reason to retry unboundedly.
    """

    code = "rate_limited"

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


class ProviderContextLengthError(ProviderError):
    """The request exceeded the model's context window."""

    code = "context_length_exceeded"


class ProviderContentFilterError(ProviderError):
    """The provider refused the request/response on content-safety grounds."""

    code = "content_filtered"


class ProviderAuthError(ProviderError):
    """The provider rejected our credentials (bad/expired API key)."""

    code = "provider_auth_failed"


class ProviderInvalidRequestError(ProviderError):
    """The provider rejected the request shape itself (not a safety/limit issue)."""

    code = "invalid_request"


class ProviderUnavailableError(ProviderError):
    """Connection failure, timeout, or a 5xx from the provider.

    This is the error every documented fallback rule (`CLAUDE.md` §9
    Fallback strategy) exists to route around — a caller seeing this
    code is the signal to fail over to the documented fallback model
    or provider, not to retry indefinitely.
    """

    code = "provider_unavailable"
