"""Postgres implementations of `domain/ports/prompt_repository.py`'s
protocols (Phase 8).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.orchestration_service.domain.eval_run import EvalRun, ExampleResult
from agentverse_api.orchestration_service.domain.golden_dataset import (
    GoldenExample,
    KeywordExpectation,
    LlmJudgeExpectation,
    RubricType,
    SchemaExpectation,
)
from agentverse_api.orchestration_service.domain.prompt import (
    PromptTemplate,
    PromptVersion,
    PromptVersionStatus,
)
from agentverse_api.orchestration_service.infrastructure.models import (
    GoldenExampleModel,
    PromptEvalRunModel,
    PromptTemplateModel,
    PromptVersionModel,
)


def _to_template(row: PromptTemplateModel) -> PromptTemplate:
    return PromptTemplate(
        id=row.id,
        slug=row.slug,
        name=row.name,
        description=row.description,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_version(row: PromptVersionModel) -> PromptVersion:
    return PromptVersion(
        id=row.id,
        prompt_template_id=row.prompt_template_id,
        version_number=row.version_number,
        system_instructions=row.system_instructions,
        model=row.model,
        temperature=row.temperature,
        status=PromptVersionStatus(row.status),
        created_at=row.created_at,
        activated_at=row.activated_at,
    )


def _expectation_to_dataclass(
    rubric: RubricType, raw: dict[str, Any]
) -> SchemaExpectation | KeywordExpectation | LlmJudgeExpectation:
    if rubric is RubricType.SCHEMA:
        return SchemaExpectation(
            required_labels=tuple(raw["required_labels"]),
            allowed_values={k: tuple(v) for k, v in raw.get("allowed_values", {}).items()},
        )
    if rubric is RubricType.KEYWORD:
        return KeywordExpectation(
            must_contain=tuple(raw.get("must_contain", ())),
            must_not_contain=tuple(raw.get("must_not_contain", ())),
        )
    return LlmJudgeExpectation(
        reference_answer=raw["reference_answer"], criteria=tuple(raw["criteria"])
    )


def _to_golden_example(row: GoldenExampleModel) -> GoldenExample:
    rubric = RubricType(row.rubric)
    return GoldenExample(
        id=row.id,
        prompt_template_id=row.prompt_template_id,
        input=row.input,
        rubric=rubric,
        expectation=_expectation_to_dataclass(rubric, row.expectation),
        created_at=row.created_at,
    )


def _to_eval_run(row: PromptEvalRunModel) -> EvalRun:
    return EvalRun(
        id=row.id,
        prompt_version_id=row.prompt_version_id,
        started_at=row.started_at,
        completed_at=row.completed_at,
        results=tuple(
            ExampleResult(
                golden_example_id=r["golden_example_id"],
                passed=r["passed"],
                reason=r["reason"],
                cost_micro_usd=r["cost_micro_usd"],
                latency_ms=r["latency_ms"],
            )
            for r in row.results
        ),
    )


class SqlPromptTemplateRepository:
    """Implements `domain.ports.prompt_repository.PromptTemplateRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, slug: str, name: str, description: str) -> PromptTemplate:
        now = datetime.now(UTC)
        row = PromptTemplateModel(
            slug=slug, name=name, description=description, created_at=now, updated_at=now
        )
        self._session.add(row)
        await self._session.flush()
        return _to_template(row)

    async def get_by_slug(self, slug: str) -> PromptTemplate | None:
        result = await self._session.execute(
            select(PromptTemplateModel).where(PromptTemplateModel.slug == slug)
        )
        row = result.scalar_one_or_none()
        return _to_template(row) if row is not None else None

    async def get_by_id(self, template_id: str) -> PromptTemplate | None:
        result = await self._session.execute(
            select(PromptTemplateModel).where(PromptTemplateModel.id == template_id)
        )
        row = result.scalar_one_or_none()
        return _to_template(row) if row is not None else None

    async def list_all(self) -> list[PromptTemplate]:
        result = await self._session.execute(
            select(PromptTemplateModel).order_by(PromptTemplateModel.name)
        )
        return [_to_template(row) for row in result.scalars()]


class SqlPromptVersionRepository:
    """Implements `domain.ports.prompt_repository.PromptVersionRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_draft(
        self,
        *,
        prompt_template_id: str,
        system_instructions: str,
        model: str,
        temperature: float | None,
    ) -> PromptVersion:
        result = await self._session.execute(
            select(PromptVersionModel)
            .where(PromptVersionModel.prompt_template_id == prompt_template_id)
            .order_by(PromptVersionModel.version_number.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        next_number = (latest.version_number + 1) if latest is not None else 1

        row = PromptVersionModel(
            prompt_template_id=prompt_template_id,
            version_number=next_number,
            system_instructions=system_instructions,
            model=model,
            temperature=temperature,
            status=PromptVersionStatus.DRAFT.value,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return _to_version(row)

    async def get_by_id(self, version_id: str) -> PromptVersion | None:
        result = await self._session.execute(
            select(PromptVersionModel).where(PromptVersionModel.id == version_id)
        )
        row = result.scalar_one_or_none()
        return _to_version(row) if row is not None else None

    async def list_for_template(self, prompt_template_id: str) -> list[PromptVersion]:
        result = await self._session.execute(
            select(PromptVersionModel)
            .where(PromptVersionModel.prompt_template_id == prompt_template_id)
            .order_by(PromptVersionModel.version_number.desc())
        )
        return [_to_version(row) for row in result.scalars()]

    async def get_active(self, prompt_template_id: str) -> PromptVersion | None:
        result = await self._session.execute(
            select(PromptVersionModel).where(
                PromptVersionModel.prompt_template_id == prompt_template_id,
                PromptVersionModel.status == PromptVersionStatus.ACTIVE.value,
            )
        )
        row = result.scalar_one_or_none()
        return _to_version(row) if row is not None else None

    async def set_status(self, *, version_id: str, status: PromptVersionStatus) -> PromptVersion:
        result = await self._session.execute(
            select(PromptVersionModel).where(PromptVersionModel.id == version_id)
        )
        row = result.scalar_one()
        row.status = status.value
        if status is PromptVersionStatus.ACTIVE:
            row.activated_at = datetime.now(UTC)
        await self._session.flush()
        return _to_version(row)


class SqlGoldenExampleRepository:
    """Implements `domain.ports.prompt_repository.GoldenExampleRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        prompt_template_id: str,
        input: dict[str, object],
        rubric: str,
        expectation: dict[str, object],
    ) -> GoldenExample:
        row = GoldenExampleModel(
            prompt_template_id=prompt_template_id,
            input=input,
            rubric=rubric,
            expectation=expectation,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return _to_golden_example(row)

    async def list_for_template(self, prompt_template_id: str) -> list[GoldenExample]:
        result = await self._session.execute(
            select(GoldenExampleModel)
            .where(GoldenExampleModel.prompt_template_id == prompt_template_id)
            .order_by(GoldenExampleModel.created_at)
        )
        return [_to_golden_example(row) for row in result.scalars()]


class SqlEvalRunRepository:
    """Implements `domain.ports.prompt_repository.EvalRunRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, run: EvalRun) -> EvalRun:
        row = PromptEvalRunModel(
            id=run.id,
            prompt_version_id=run.prompt_version_id,
            started_at=run.started_at,
            completed_at=run.completed_at,
            results=[
                {
                    "golden_example_id": r.golden_example_id,
                    "passed": r.passed,
                    "reason": r.reason,
                    "cost_micro_usd": r.cost_micro_usd,
                    "latency_ms": r.latency_ms,
                }
                for r in run.results
            ],
        )
        self._session.add(row)
        await self._session.flush()
        return _to_eval_run(row)

    async def latest_for_version(self, prompt_version_id: str) -> EvalRun | None:
        result = await self._session.execute(
            select(PromptEvalRunModel)
            .where(PromptEvalRunModel.prompt_version_id == prompt_version_id)
            .order_by(PromptEvalRunModel.started_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return _to_eval_run(row) if row is not None else None
