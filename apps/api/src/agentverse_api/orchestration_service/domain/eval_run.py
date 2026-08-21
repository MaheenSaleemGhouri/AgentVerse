"""One regression run of a prompt version against its golden dataset.

Pure — aggregation only, no I/O. `application/eval_harness/
regression_runner.py` is what actually calls the provider per example
and builds these; this module just states what "passed" means once
every example's own score is known.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ExampleResult:
    """One golden example's outcome within a run — carries cost/latency
    per CLAUDE.md §9's "cost and latency tracked per prompt variant",
    at the per-example grain so a slow or expensive single example is
    visible, not just buried in the run total.
    """

    golden_example_id: str
    passed: bool
    reason: str
    cost_micro_usd: int
    latency_ms: int


@dataclass(frozen=True, slots=True)
class EvalRun:
    """A prompt version cannot be promoted (`promote_prompt_version.py`)
    without one of these existing for it with `passed=True` — the "CI-
    style gate" docs/roadmap.md PHASE 8 names.

    `passed` is true only when every example passed — a version that
    fails even one golden example is not eval-passing, matching the
    acceptance criterion's "a prompt version fails its golden-dataset
    eval" phrasing (singular failure blocks promotion, not a majority
    threshold a prompt engineer could game by adding easy examples).
    """

    id: str
    prompt_version_id: str
    started_at: datetime
    completed_at: datetime | None
    results: tuple[ExampleResult, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return len(self.results) > 0 and all(r.passed for r in self.results)

    @property
    def total_examples(self) -> int:
        return len(self.results)

    @property
    def passed_examples(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total_cost_micro_usd(self) -> int:
        return sum(r.cost_micro_usd for r in self.results)

    @property
    def total_latency_ms(self) -> int:
        return sum(r.latency_ms for r in self.results)
