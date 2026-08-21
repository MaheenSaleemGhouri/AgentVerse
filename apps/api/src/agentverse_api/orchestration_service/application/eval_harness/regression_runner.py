"""Runs a prompt version against its template's golden dataset and
records the result — the eval harness itself (docs/roadmap.md PHASE 8's
named deliverable). Every LLM call goes through `ProviderAdapter`
(CLAUDE.md Rule 16), never a provider SDK directly.

Triggered whenever a prompt's text changes (a new `DRAFT` version) *and*
whenever the target model version changes, per the acceptance
criterion "when the regression runner is triggered, then the full eval
suite re-runs, not only on prompt-text changes" — this module has no
opinion on *when* it's called; `promote_prompt_version.py` and any
future scheduled re-run both call the same `run()`.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from agentverse_shared.cost_accounting import calculate_cost_micro_usd

from agentverse_api.orchestration_service.application.eval_harness.llm_judge import (
    score_llm_judge,
)
from agentverse_api.orchestration_service.domain.entities import ChatMessage, ChatRequest
from agentverse_api.orchestration_service.domain.eval_run import EvalRun, ExampleResult
from agentverse_api.orchestration_service.domain.eval_scoring import score_keyword, score_schema
from agentverse_api.orchestration_service.domain.golden_dataset import (
    KeywordExpectation,
    LlmJudgeExpectation,
    RubricType,
    SchemaExpectation,
)
from agentverse_api.orchestration_service.domain.ports.prompt_repository import (
    EvalRunRepository,
    GoldenExampleRepository,
    PromptVersionRepository,
)
from agentverse_api.orchestration_service.domain.ports.provider_adapter import ProviderAdapter
from agentverse_api.orchestration_service.domain.prompt import PromptVersionNotFoundError

__all__ = ["NoGoldenExamplesError", "PromptVersionNotFoundError", "RegressionRunner"]


class NoGoldenExamplesError(Exception):
    """A template with zero golden examples cannot be eval-gated at
    all — running the harness against nothing and calling it a pass
    would be exactly the silent-drift risk CLAUDE.md §9 warns about.
    Maps to HTTP 422.
    """

    def __init__(self, prompt_template_id: str) -> None:
        self.prompt_template_id = prompt_template_id
        super().__init__(f"Template {prompt_template_id!r} has no golden examples to run against")


def _render_input(input: dict[str, object]) -> str:
    """Deterministic, generic rendering — every golden example's input
    is `{field: value}`; the harness has no per-template knowledge of
    what those fields mean, matching `regression_runner`'s own
    module docstring: input-shape agnostic.
    """
    return "\n".join(f"{key}: {value}" for key, value in input.items())


@dataclass(slots=True)
class RegressionRunner:
    provider: ProviderAdapter
    versions: PromptVersionRepository
    golden_examples: GoldenExampleRepository
    eval_runs: EvalRunRepository

    async def run(self, *, prompt_version_id: str) -> EvalRun:
        version = await self.versions.get_by_id(prompt_version_id)
        if version is None:
            raise PromptVersionNotFoundError(prompt_version_id)

        examples = await self.golden_examples.list_for_template(version.prompt_template_id)
        if not examples:
            raise NoGoldenExamplesError(version.prompt_template_id)

        started_at = datetime.now(UTC)
        results: list[ExampleResult] = []
        for example in examples:
            request = ChatRequest(
                model=version.model,
                temperature=version.temperature,
                messages=[
                    ChatMessage(role="system", content=version.system_instructions),
                    ChatMessage(role="user", content=_render_input(example.input)),
                ],
            )
            call_started = time.monotonic()
            result = await self.provider.chat(request)
            latency_ms = int((time.monotonic() - call_started) * 1000)
            cost_micro_usd = calculate_cost_micro_usd(version.model, result.usage)

            if example.rubric is RubricType.SCHEMA:
                assert isinstance(example.expectation, SchemaExpectation)  # noqa: S101 - repo invariant
                score = score_schema(result.content, example.expectation)
            elif example.rubric is RubricType.KEYWORD:
                assert isinstance(example.expectation, KeywordExpectation)  # noqa: S101 - repo invariant
                score = score_keyword(result.content, example.expectation)
            else:
                assert isinstance(example.expectation, LlmJudgeExpectation)  # noqa: S101 - repo invariant
                score = await score_llm_judge(
                    adapter=self.provider,
                    candidate_output=result.content,
                    expectation=example.expectation,
                )

            results.append(
                ExampleResult(
                    golden_example_id=example.id,
                    passed=score.passed,
                    reason=score.reason,
                    cost_micro_usd=cost_micro_usd,
                    latency_ms=latency_ms,
                )
            )

        run = EvalRun(
            id=str(uuid.uuid4()),
            prompt_version_id=prompt_version_id,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            results=tuple(results),
        )
        return await self.eval_runs.record(run)
