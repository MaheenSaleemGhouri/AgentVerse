"""Token usage -> cost. The single source every later consumer (Phase 4's
run-cost display, Phase 7's billing aggregation) must import — never
recompute inline, per this phase's roadmap risk note and CLAUDE.md Rule 3
(DRY: one source of truth, never duplicated business logic).

Pure functions, zero I/O: CLAUDE.md §11 requires cost calculation be
unit-testable without touching a provider or a database.

Unit note (deliberate, not a Rule 15 violation): CLAUDE.md Rule 15 says
money is always integer cents, never floats — that rule protects *stored,
invoiced* amounts. A single LLM call routinely costs a fraction of one
cent (e.g. gpt-4o-mini's per-call cost at typical prompt sizes), so
rounding each call to whole integer cents here would round nearly every
call to zero and silently destroy the very accounting Phase 7 aggregates
over thousands of calls. Following the same integer-only discipline at a
finer grain, this module returns cost in **micro-USD** (1 unit =
$0.000001) as an integer — still never a float, just a smaller unit than
cents. Phase 7 sums micro-USD across `billing_usage_events` and converts
to integer cents only once, at the final invoice/rounding boundary
(`micro_usd_to_cents`), which is exactly where Rule 15's "integer cents"
requirement actually applies.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_api.orchestration_service.domain.entities import TokenUsage


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Micro-USD per 1,000 tokens. `pricing_version` is a snapshot date,
    not a guarantee of current accuracy — real invoicing in Phase 7 must
    reconcile this table against the provider's published pricing page
    before it is ever used to bill a workspace (`billing-expert` review
    required at that phase, not assumed here).
    """

    prompt_micro_usd_per_1k: int
    completion_micro_usd_per_1k: int
    pricing_version: str


# Snapshot pricing, in micro-USD per 1,000 tokens. Source: OpenAI's
# published per-token pricing at the `pricing_version` date below.
# MUST be reconciled by `billing-expert` before Phase 7 bills anyone.
MODEL_PRICING: dict[str, ModelPricing] = {
    "gpt-4o-mini": ModelPricing(
        prompt_micro_usd_per_1k=150,
        completion_micro_usd_per_1k=600,
        pricing_version="2026-01-01",
    ),
    "gpt-4o": ModelPricing(
        prompt_micro_usd_per_1k=2500,
        completion_micro_usd_per_1k=10000,
        pricing_version="2026-01-01",
    ),
}


class UnknownModelPricingError(Exception):
    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__(f"No pricing entry for model {model!r}")


def calculate_cost_micro_usd(model: str, usage: TokenUsage) -> int:
    """Cost of one call, in integer micro-USD. Raises `UnknownModelPricingError`
    rather than silently returning zero for an unpriced model — a silent
    zero-cost call is exactly the "silent drift" risk this phase's roadmap
    entry warns about.
    """
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        raise UnknownModelPricingError(model)

    prompt_cost = (usage.prompt_tokens * pricing.prompt_micro_usd_per_1k) // 1000
    completion_cost = (usage.completion_tokens * pricing.completion_micro_usd_per_1k) // 1000
    return prompt_cost + completion_cost


def micro_usd_to_cents(micro_usd: int) -> int:
    """Converts accumulated micro-USD to integer cents, rounding to the
    nearest cent. This is the *only* point where a micro-USD total should
    ever become a cents value — call it once, at final aggregation
    (Phase 7), never per-call.
    """
    # 1 cent = 10_000 micro-USD. Round-half-up on integer division.
    return (micro_usd + 5_000) // 10_000
