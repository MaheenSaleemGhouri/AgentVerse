"""Pure-function tests — zero I/O, zero real API key (CLAUDE.md §11)."""

from __future__ import annotations

import httpx
import openai
import pytest

from agents.extensions.models.litellm_model import LitellmModel
from agentverse_worker.agents.model_resolution import (
    UnsupportedProviderError,
    resolve_model,
    translate_run_exception,
)


def test_resolve_model_openai_string_passes_through_unchanged() -> None:
    assert resolve_model("gpt-4o-mini", anthropic_api_key=None) == "gpt-4o-mini"
    assert resolve_model("gpt-4.1", anthropic_api_key="sk-anthropic-key") == "gpt-4.1"


def test_resolve_model_anthropic_returns_litellm_model() -> None:
    result = resolve_model("anthropic/claude-haiku-4-5", anthropic_api_key="sk-ant-key")
    assert isinstance(result, LitellmModel)
    assert result.model == "anthropic/claude-haiku-4-5"
    assert result.api_key == "sk-ant-key"


def test_resolve_model_anthropic_without_key_raises() -> None:
    with pytest.raises(UnsupportedProviderError) as exc_info:
        resolve_model("anthropic/claude-haiku-4-5", anthropic_api_key=None)
    assert exc_info.value.model == "anthropic/claude-haiku-4-5"


def test_resolve_model_unknown_provider_prefix_raises() -> None:
    with pytest.raises(UnsupportedProviderError) as exc_info:
        resolve_model("mistral/mistral-large", anthropic_api_key="sk-ant-key")
    assert "mistral/" in exc_info.value.reason


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def test_translate_run_exception_rate_limit() -> None:
    response = httpx.Response(status_code=429, request=_request())
    exc = openai.RateLimitError("rate limited", response=response, body=None)
    assert translate_run_exception(exc).startswith("rate_limited:")


def test_translate_run_exception_auth_failure() -> None:
    response = httpx.Response(status_code=401, request=_request())
    exc = openai.AuthenticationError("bad key", response=response, body=None)
    assert translate_run_exception(exc).startswith("provider_auth_failed:")


def test_translate_run_exception_context_length() -> None:
    response = httpx.Response(status_code=400, request=_request())
    exc = openai.BadRequestError("maximum context length exceeded", response=response, body=None)
    assert translate_run_exception(exc).startswith("context_length_exceeded:")


def test_translate_run_exception_other_bad_request() -> None:
    response = httpx.Response(status_code=400, request=_request())
    exc = openai.BadRequestError("invalid tool schema", response=response, body=None)
    assert translate_run_exception(exc).startswith("invalid_request:")


def test_translate_run_exception_connection_error() -> None:
    exc = openai.APIConnectionError(request=_request())
    assert translate_run_exception(exc).startswith("provider_unavailable:")


def test_translate_run_exception_unrecognized_exception_falls_through() -> None:
    exc = ValueError("some unrelated bug")
    assert translate_run_exception(exc) == "some unrelated bug"
