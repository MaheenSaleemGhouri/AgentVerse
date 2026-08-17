"""Token usage -> cost. The single source every consumer across every
service (apps/api's run-cost display, apps/worker's run executor,
Phase 7's billing aggregation) must import — never recompute inline
(CLAUDE.md Rule 3: DRY, one source of truth). Originally built in
apps/api's Phase 2; moved here in Phase 4 once apps/worker's own
executor needed the identical calculation, not just a compatible one —
the same "shared internal package" reasoning as `locks.distributed_lock`.

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


@dataclass(frozen=True, slots=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


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
#
# `gpt-4.1`/`gpt-4.1-mini` were already offered by the agent-builder model
# picker (apps/web/lib/validation/agent-config.ts) with no matching entry
# here, so selecting either raised `UnknownModelPricingError` on every run
# — a pre-existing bug, fixed alongside Phase 11's Anthropic entries below
# rather than left in place while this table was already being touched.
#
# Anthropic entries are keyed by the `anthropic/<model-id>` strings
# `apps/worker`'s `resolve_model()` resolves to a `LitellmModel` — see
# that module's docstring for the provider-prefix convention. Pricing is
# Anthropic's standing (non-promotional) published per-token rate.
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
    "gpt-4.1-mini": ModelPricing(
        prompt_micro_usd_per_1k=400,
        completion_micro_usd_per_1k=1600,
        pricing_version="2026-01-01",
    ),
    "gpt-4.1": ModelPricing(
        prompt_micro_usd_per_1k=2000,
        completion_micro_usd_per_1k=8000,
        pricing_version="2026-01-01",
    ),
    "anthropic/claude-haiku-4-5": ModelPricing(
        prompt_micro_usd_per_1k=1000,
        completion_micro_usd_per_1k=5000,
        pricing_version="2026-01-01",
    ),
    "anthropic/claude-sonnet-5": ModelPricing(
        prompt_micro_usd_per_1k=3000,
        completion_micro_usd_per_1k=15000,
        pricing_version="2026-01-01",
    ),
}


#: Usable context window per model, in tokens. Lives beside pricing
#: because it answers the same kind of question — a property of the model
#: the platform must know before it can call it — and because both are
#: read by the same callers. Retrieval's context budget is computed by
#: subtraction from this, so a missing entry must raise rather than
#: default: a guessed window either wastes budget or overflows the call.
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "gpt-4o-mini": 128_000,
    "gpt-4o": 128_000,
    "gpt-4.1-mini": 1_047_576,
    "gpt-4.1": 1_047_576,
    "anthropic/claude-haiku-4-5": 200_000,
    "anthropic/claude-sonnet-5": 1_000_000,
}


class UnknownModelPricingError(Exception):
    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__(f"No pricing entry for model {model!r}")


class UnknownModelWindowError(Exception):
    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__(f"No context-window entry for model {model!r}")


def context_window_for(model: str) -> int:
    window = MODEL_CONTEXT_WINDOWS.get(model)
    if window is None:
        raise UnknownModelWindowError(model)
    return window


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
