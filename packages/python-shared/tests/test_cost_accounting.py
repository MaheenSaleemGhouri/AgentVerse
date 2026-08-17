"""Pure-function tests — zero I/O (CLAUDE.md §11)."""

from __future__ import annotations

import pytest

from agentverse_shared.cost_accounting import (
    MODEL_CONTEXT_WINDOWS,
    MODEL_PRICING,
    TokenUsage,
    UnknownModelPricingError,
    UnknownModelWindowError,
    calculate_cost_micro_usd,
    context_window_for,
    micro_usd_to_cents,
)


def test_calculate_cost_micro_usd_known_model() -> None:
    usage = TokenUsage(prompt_tokens=1000, completion_tokens=1000)
    cost = calculate_cost_micro_usd("gpt-4o-mini", usage)
    assert cost == 150 + 600


def test_calculate_cost_micro_usd_zero_usage() -> None:
    usage = TokenUsage(prompt_tokens=0, completion_tokens=0)
    assert calculate_cost_micro_usd("gpt-4o-mini", usage) == 0


def test_calculate_cost_micro_usd_unknown_model_raises() -> None:
    usage = TokenUsage(prompt_tokens=10, completion_tokens=10)
    with pytest.raises(UnknownModelPricingError):
        calculate_cost_micro_usd("not-a-real-model", usage)


def test_calculate_cost_micro_usd_sub_thousand_tokens_is_not_silently_zero() -> None:
    # A tiny call still accrues a nonzero micro-USD cost — this is
    # exactly the precision integer *cents* per call would destroy.
    usage = TokenUsage(prompt_tokens=10, completion_tokens=0)
    cost = calculate_cost_micro_usd("gpt-4o-mini", usage)
    assert cost == 1  # (10 * 150) // 1000 == 1


def test_micro_usd_to_cents_rounds_half_up() -> None:
    assert micro_usd_to_cents(0) == 0
    assert micro_usd_to_cents(4_999) == 0
    assert micro_usd_to_cents(5_000) == 1
    assert micro_usd_to_cents(10_000) == 1
    assert micro_usd_to_cents(15_000) == 2


@pytest.mark.parametrize(
    "model",
    [
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4.1-mini",
        "gpt-4.1",
        "anthropic/claude-haiku-4-5",
        "anthropic/claude-sonnet-5",
    ],
)
def test_every_agent_builder_model_has_pricing_and_window(model: str) -> None:
    # Regression guard for the pre-existing bug this phase fixed: gpt-4.1
    # and gpt-4.1-mini were already selectable in the UI with no entry
    # here, so every run against them raised UnknownModelPricingError.
    assert model in MODEL_PRICING
    assert model in MODEL_CONTEXT_WINDOWS
    usage = TokenUsage(prompt_tokens=1000, completion_tokens=1000)
    cost = calculate_cost_micro_usd(model, usage)
    assert cost > 0
    assert context_window_for(model) > 0


def test_calculate_cost_micro_usd_anthropic_model() -> None:
    usage = TokenUsage(prompt_tokens=1000, completion_tokens=1000)
    cost = calculate_cost_micro_usd("anthropic/claude-haiku-4-5", usage)
    assert cost == 1000 + 5000


def test_context_window_for_unknown_model_raises() -> None:
    with pytest.raises(UnknownModelWindowError):
        context_window_for("not-a-real-model")
