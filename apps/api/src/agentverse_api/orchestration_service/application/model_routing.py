"""Model-selection routing-table SCAFFOLD (roadmap Phase 2 Features:
"a routing table shape, not yet consumed by any orchestration logic").

This fixes the *shape* Phase 9 (multi-agent orchestration & model
routing) will consume — cheap/fast models for classification and
tool-selection, the strongest model reserved for final synthesis
(CLAUDE.md §9 Cost Optimization). No orchestration, runtime, or route
code reads from `ROUTING_TABLE` yet; doing so before Phase 9 would be
out of this phase's scope.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelRoute:
    model: str
    fallback_model: str


# task_type -> ModelRoute. Deliberately unconsumed until Phase 9.
ROUTING_TABLE: dict[str, ModelRoute] = {
    "classification": ModelRoute(model="gpt-4o-mini", fallback_model="gpt-4o-mini"),
    "tool_selection": ModelRoute(model="gpt-4o-mini", fallback_model="gpt-4o"),
    "synthesis": ModelRoute(model="gpt-4o", fallback_model="gpt-4o-mini"),
}

# The only model this phase's internal test route uses by default.
DEFAULT_MODEL = "gpt-4o-mini"
