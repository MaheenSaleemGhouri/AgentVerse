"""Resolves a stored `agent_versions.config["model"]` string to whatever
the OpenAI Agents SDK's `Agent(model=...)` actually needs (Phase 11's
second provider).

Convention shared with `packages/python-shared`'s `cost_accounting.py`
and `apps/web`'s `MODEL_CATALOG`: a model string with no `/` is OpenAI,
resolved exactly as before (a plain string, letting the SDK's own default
resolution handle it — zero behavior change for every agent configured
before this phase). An `anthropic/`-prefixed string routes through the
SDK's own vendored LiteLLM extension (`agents.extensions.models.litellm_
model.LitellmModel`, present since `openai-agents==0.18.3` — this phase
only adds the `litellm` package itself via the `[litellm]` extra).

Pure resolution logic — no network call happens here. Constructing a
`LitellmModel` just stores its arguments; the SDK invokes it later. This
keeps the function unit-testable (CLAUDE.md §11) without a real API key
or a live provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import openai

from agents.extensions.models.litellm_model import LitellmModel

if TYPE_CHECKING:
    from agents.models.interface import Model

_ANTHROPIC_PREFIX = "anthropic/"


class UnsupportedProviderError(Exception):
    """Raised for a model string this worker cannot resolve — an
    unrecognized provider prefix, or a recognized one with no
    credentials configured. Caught by `agent_run_job.py`'s existing
    `except Exception` boundary and recorded as a normal run failure,
    never left to propagate as a raw `KeyError`/`AttributeError`.
    """

    def __init__(self, model: str, *, reason: str) -> None:
        self.model = model
        self.reason = reason
        super().__init__(f"Cannot resolve model {model!r}: {reason}")


def resolve_model(model: str, *, anthropic_api_key: str | None) -> str | Model:
    """Returns either the original string (OpenAI, the SDK's default
    path) or a `Model` instance (Anthropic, via LiteLLM) for
    `Agent(model=...)`.
    """
    if "/" not in model:
        return model

    provider_prefix = model.split("/", 1)[0] + "/"
    if provider_prefix != _ANTHROPIC_PREFIX:
        raise UnsupportedProviderError(model, reason=f"no adapter for provider {provider_prefix!r}")
    if anthropic_api_key is None:
        raise UnsupportedProviderError(
            model, reason="Anthropic is not configured (AGENTVERSE_WORKER_ANTHROPIC_API_KEY unset)"
        )
    return LitellmModel(model=model, api_key=anthropic_api_key)


# Reused as the run-failure vocabulary's stable bucket names — identical
# to `orchestration_service.domain.provider_errors`' `.code` taxonomy on
# the API side, so a run failure reads the same way regardless of which
# service caught it (CLAUDE.md §9: provider errors translated at the
# boundary, one taxonomy).
_RATE_LIMITED = "rate_limited"
_AUTH_FAILED = "provider_auth_failed"
_CONTEXT_LENGTH = "context_length_exceeded"
_INVALID_REQUEST = "invalid_request"
_UNAVAILABLE = "provider_unavailable"


def translate_run_exception(exc: Exception) -> str:
    """Normalizes a provider-layer exception surfacing during a run into
    a short, stable-prefixed reason string for `agent_run_steps.payload`/
    `agent_runs.error_message`.

    LiteLLM's exceptions subclass the `openai` SDK's own exception
    hierarchy by design (LiteLLM's own compatibility goal, and the same
    reason `LitellmModel.get_retry_advice` reuses `openai`'s retry-advice
    helper) — this worker already depends on `openai` directly, so
    checking against `openai.*` exception types covers both an
    OpenAI-routed run's own SDK exceptions and a LiteLLM/Anthropic-routed
    run's exceptions with one set of branches, never a second parallel
    translation table.

    Any exception outside this taxonomy (a genuine bug, not a provider
    failure) falls through to `str(exc)` unchanged — this function only
    narrows *known* provider-failure shapes, it never hides an
    unrecognized error.
    """
    if isinstance(exc, openai.RateLimitError):
        return f"{_RATE_LIMITED}: {exc}"
    if isinstance(exc, openai.AuthenticationError):
        return f"{_AUTH_FAILED}: {exc}"
    if isinstance(exc, openai.BadRequestError):
        message = str(exc).lower()
        if "context" in message and ("length" in message or "maximum" in message):
            return f"{_CONTEXT_LENGTH}: {exc}"
        return f"{_INVALID_REQUEST}: {exc}"
    if isinstance(exc, openai.APIConnectionError | openai.InternalServerError):
        return f"{_UNAVAILABLE}: {exc}"
    return str(exc)
