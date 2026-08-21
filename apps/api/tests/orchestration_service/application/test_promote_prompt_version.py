"""`promote_prompt_version` — the CI-style gate (docs/roadmap.md PHASE
8), against fake repos."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tests.fakes.prompt_repository import FakeEvalRunRepository, FakePromptVersionRepository

from agentverse_api.orchestration_service.application.promote_prompt_version import (
    PromptVersionFailedEvalError,
    PromptVersionNotEvaluatedError,
    promote_prompt_version,
)
from agentverse_api.orchestration_service.domain.eval_run import EvalRun, ExampleResult
from agentverse_api.orchestration_service.domain.prompt import (
    InvalidPromptVersionTransitionError,
    PromptVersionNotFoundError,
    PromptVersionStatus,
)

_T0 = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def _passing_run(version_id: str) -> EvalRun:
    return EvalRun(
        id="run-pass",
        prompt_version_id=version_id,
        started_at=_T0,
        completed_at=_T0,
        results=(ExampleResult("ex-1", passed=True, reason="ok", cost_micro_usd=1, latency_ms=1),),
    )


def _failing_run(version_id: str) -> EvalRun:
    return EvalRun(
        id="run-fail",
        prompt_version_id=version_id,
        started_at=_T0,
        completed_at=_T0,
        results=(
            ExampleResult("ex-1", passed=False, reason="nope", cost_micro_usd=1, latency_ms=1),
        ),
    )


class TestPromote:
    async def test_a_version_that_does_not_exist_raises(self) -> None:
        with pytest.raises(PromptVersionNotFoundError):
            await promote_prompt_version(
                version_id="does-not-exist",
                versions=FakePromptVersionRepository(),
                eval_runs=FakeEvalRunRepository(),
            )

    async def test_a_version_never_evaluated_cannot_be_promoted(self) -> None:
        versions = FakePromptVersionRepository()
        version = await versions.create_draft(
            prompt_template_id="tmpl-1",
            system_instructions="x",
            model="gpt-4o-mini",
            temperature=None,
        )
        with pytest.raises(PromptVersionNotEvaluatedError):
            await promote_prompt_version(
                version_id=version.id, versions=versions, eval_runs=FakeEvalRunRepository()
            )

    async def test_a_version_whose_latest_eval_failed_cannot_be_promoted(self) -> None:
        versions = FakePromptVersionRepository()
        version = await versions.create_draft(
            prompt_template_id="tmpl-1",
            system_instructions="x",
            model="gpt-4o-mini",
            temperature=None,
        )
        eval_runs = FakeEvalRunRepository()
        await eval_runs.record(_failing_run(version.id))

        with pytest.raises(PromptVersionFailedEvalError) as exc_info:
            await promote_prompt_version(
                version_id=version.id, versions=versions, eval_runs=eval_runs
            )
        assert exc_info.value.eval_run_id == "run-fail"

    async def test_a_version_with_a_passing_eval_is_promoted_to_active(self) -> None:
        versions = FakePromptVersionRepository()
        version = await versions.create_draft(
            prompt_template_id="tmpl-1",
            system_instructions="x",
            model="gpt-4o-mini",
            temperature=None,
        )
        eval_runs = FakeEvalRunRepository()
        await eval_runs.record(_passing_run(version.id))

        result = await promote_prompt_version(
            version_id=version.id, versions=versions, eval_runs=eval_runs
        )

        assert result.version.status is PromptVersionStatus.ACTIVE
        assert result.archived_version is None

    async def test_promoting_a_new_version_archives_the_previously_active_one(self) -> None:
        versions = FakePromptVersionRepository()
        eval_runs = FakeEvalRunRepository()

        v1 = await versions.create_draft(
            prompt_template_id="tmpl-1",
            system_instructions="v1",
            model="gpt-4o-mini",
            temperature=None,
        )
        await eval_runs.record(_passing_run(v1.id))
        await promote_prompt_version(version_id=v1.id, versions=versions, eval_runs=eval_runs)

        v2 = await versions.create_draft(
            prompt_template_id="tmpl-1",
            system_instructions="v2",
            model="gpt-4o-mini",
            temperature=None,
        )
        await eval_runs.record(_passing_run(v2.id))
        result = await promote_prompt_version(
            version_id=v2.id, versions=versions, eval_runs=eval_runs
        )

        assert result.version.status is PromptVersionStatus.ACTIVE
        assert result.archived_version is not None
        assert result.archived_version.id == v1.id
        assert result.archived_version.status is PromptVersionStatus.ARCHIVED
        # Only one active version per template, ever.
        assert await versions.get_active("tmpl-1") == result.version

    async def test_an_already_active_version_cannot_be_promoted_again(self) -> None:
        versions = FakePromptVersionRepository()
        eval_runs = FakeEvalRunRepository()
        version = await versions.create_draft(
            prompt_template_id="tmpl-1",
            system_instructions="x",
            model="gpt-4o-mini",
            temperature=None,
        )
        await eval_runs.record(_passing_run(version.id))
        await promote_prompt_version(version_id=version.id, versions=versions, eval_runs=eval_runs)

        with pytest.raises(InvalidPromptVersionTransitionError):
            await promote_prompt_version(
                version_id=version.id, versions=versions, eval_runs=eval_runs
            )

    async def test_only_the_latest_eval_run_counts_an_old_failure_does_not_block_a_later_pass(
        self,
    ) -> None:
        versions = FakePromptVersionRepository()
        eval_runs = FakeEvalRunRepository()
        version = await versions.create_draft(
            prompt_template_id="tmpl-1",
            system_instructions="x",
            model="gpt-4o-mini",
            temperature=None,
        )
        old_failure = EvalRun(
            id="run-old",
            prompt_version_id=version.id,
            started_at=datetime(2026, 8, 20, 0, 0, tzinfo=UTC),
            completed_at=datetime(2026, 8, 20, 0, 0, tzinfo=UTC),
            results=(
                ExampleResult("ex-1", passed=False, reason="x", cost_micro_usd=1, latency_ms=1),
            ),
        )
        await eval_runs.record(old_failure)
        await eval_runs.record(_passing_run(version.id))

        result = await promote_prompt_version(
            version_id=version.id, versions=versions, eval_runs=eval_runs
        )
        assert result.version.status is PromptVersionStatus.ACTIVE
