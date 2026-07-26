"""Pure-function tests — zero I/O (CLAUDE.md §11)."""

from __future__ import annotations

import pytest

from agentverse_api.orchestration_service.application.cost_accounting import (
    UnknownModelPricingError,
    calculate_cost_micro_usd,
    micro_usd_to_cents,
)
from agentverse_api.orchestration_service.domain.entities import TokenUsage


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
