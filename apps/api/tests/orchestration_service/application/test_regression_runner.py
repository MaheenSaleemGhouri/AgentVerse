"""`RegressionRunner` against a fake `ProviderAdapter` and fake repos —
never a real LLM call (CLAUDE.md §11)."""

from __future__ import annotations

import pytest
from agentverse_shared.cost_accounting import TokenUsage
from tests.fakes.prompt_repository import (
    FakeEvalRunRepository,
    FakeGoldenExampleRepository,
    FakePromptVersionRepository,
)
from tests.fakes.provider_adapter import FakeProviderAdapter

from agentverse_api.orchestration_service.application.eval_harness.regression_runner import (
    NoGoldenExamplesError,
    PromptVersionNotFoundError,
    RegressionRunner,
)
from agentverse_api.orchestration_service.domain.entities import ChatResult
from agentverse_api.orchestration_service.domain.prompt import PromptVersion


async def _draft_version(
    versions: FakePromptVersionRepository, *, template_id: str = "tmpl-1"
) -> PromptVersion:
    return await versions.create_draft(
        prompt_template_id=template_id,
        system_instructions="You triage tickets.",
        model="gpt-4o-mini",
        temperature=0.0,
    )


def _result(content: str) -> ChatResult:
    return ChatResult(
        content=content,
        usage=TokenUsage(prompt_tokens=50, completion_tokens=20),
        finish_reason="stop",
    )


def _runner(
    provider: FakeProviderAdapter,
    versions: FakePromptVersionRepository,
    golden_examples: FakeGoldenExampleRepository,
    eval_runs: FakeEvalRunRepository,
) -> RegressionRunner:
    return RegressionRunner(
        provider=provider, versions=versions, golden_examples=golden_examples, eval_runs=eval_runs
    )


class TestRun:
    async def test_a_version_that_does_not_exist_raises(self) -> None:
        runner = _runner(
            FakeProviderAdapter(),
            FakePromptVersionRepository(),
            FakeGoldenExampleRepository(),
            FakeEvalRunRepository(),
        )
        with pytest.raises(PromptVersionNotFoundError):
            await runner.run(prompt_version_id="does-not-exist")

    async def test_a_template_with_no_golden_examples_refuses_to_run(self) -> None:
        versions = FakePromptVersionRepository()
        version = await _draft_version(versions)
        runner = _runner(
            FakeProviderAdapter(), versions, FakeGoldenExampleRepository(), FakeEvalRunRepository()
        )
        with pytest.raises(NoGoldenExamplesError):
            await runner.run(prompt_version_id=version.id)

    async def test_a_run_where_every_example_passes_is_recorded_as_passed(self) -> None:
        versions = FakePromptVersionRepository()
        version = await _draft_version(versions)
        golden_examples = FakeGoldenExampleRepository()
        await golden_examples.add(
            prompt_template_id=version.prompt_template_id,
            input={"subject": "billing issue"},
            rubric="schema",
            expectation={"required_labels": ["category"]},
        )
        provider = FakeProviderAdapter(chat_result=_result("category: billing"))
        eval_runs = FakeEvalRunRepository()
        runner = _runner(provider, versions, golden_examples, eval_runs)

        run = await runner.run(prompt_version_id=version.id)

        assert run.passed is True
        assert run.total_examples == 1
        assert eval_runs.runs == [run]

    async def test_a_run_where_one_example_fails_is_recorded_as_failed(self) -> None:
        versions = FakePromptVersionRepository()
        version = await _draft_version(versions)
        golden_examples = FakeGoldenExampleRepository()
        await golden_examples.add(
            prompt_template_id=version.prompt_template_id,
            input={"subject": "billing issue"},
            rubric="schema",
            expectation={"required_labels": ["category"]},
        )
        # No `category:` line at all — the parser finds nothing.
        provider = FakeProviderAdapter(chat_result=_result("I am not sure what to say."))
        runner = _runner(provider, versions, golden_examples, FakeEvalRunRepository())

        run = await runner.run(prompt_version_id=version.id)

        assert run.passed is False
        assert run.results[0].passed is False

    async def test_cost_and_latency_are_recorded_per_example(self) -> None:
        versions = FakePromptVersionRepository()
        version = await _draft_version(versions)
        golden_examples = FakeGoldenExampleRepository()
        await golden_examples.add(
            prompt_template_id=version.prompt_template_id,
            input={"subject": "x"},
            rubric="keyword",
            expectation={"must_contain": []},
        )
        provider = FakeProviderAdapter(chat_result=_result("anything"))
        runner = _runner(provider, versions, golden_examples, FakeEvalRunRepository())

        run = await runner.run(prompt_version_id=version.id)

        # gpt-4o-mini: 50 prompt + 20 completion tokens at the pricing
        # table's per-1k rates — a real, non-zero cost, not a stub.
        assert run.results[0].cost_micro_usd > 0
        assert run.results[0].latency_ms >= 0

    async def test_multiple_golden_examples_each_get_their_own_provider_call(self) -> None:
        versions = FakePromptVersionRepository()
        version = await _draft_version(versions)
        golden_examples = FakeGoldenExampleRepository()
        for i in range(3):
            await golden_examples.add(
                prompt_template_id=version.prompt_template_id,
                input={"subject": f"ticket {i}"},
                rubric="keyword",
                expectation={"must_contain": []},
            )
        provider = FakeProviderAdapter(chat_result=_result("anything"))
        runner = _runner(provider, versions, golden_examples, FakeEvalRunRepository())

        run = await runner.run(prompt_version_id=version.id)

        assert run.total_examples == 3
        assert len(provider.requests) == 3
