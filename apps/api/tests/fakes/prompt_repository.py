"""In-memory fakes implementing `domain/ports/prompt_repository.py`'s
protocols — used by unit tests so application-layer logic (the eval
harness, the promotion gate) is tested without I/O (CLAUDE.md §11).
Integration tests use the real `Sql*Repository` classes against
Postgres instead.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from agentverse_api.orchestration_service.domain.eval_run import EvalRun
from agentverse_api.orchestration_service.domain.golden_dataset import GoldenExample, RubricType
from agentverse_api.orchestration_service.domain.prompt import (
    PromptTemplate,
    PromptVersion,
    PromptVersionStatus,
)


@dataclass
class FakePromptTemplateRepository:
    templates: dict[str, PromptTemplate] = field(default_factory=dict)

    async def create(self, *, slug: str, name: str, description: str) -> PromptTemplate:
        now = datetime.now(UTC)
        template = PromptTemplate(
            id=str(uuid.uuid4()),
            slug=slug,
            name=name,
            description=description,
            created_at=now,
            updated_at=now,
        )
        self.templates[template.id] = template
        return template

    async def get_by_slug(self, slug: str) -> PromptTemplate | None:
        return next((t for t in self.templates.values() if t.slug == slug), None)

    async def get_by_id(self, template_id: str) -> PromptTemplate | None:
        return self.templates.get(template_id)

    async def list_all(self) -> list[PromptTemplate]:
        return list(self.templates.values())


@dataclass
class FakePromptVersionRepository:
    versions: dict[str, PromptVersion] = field(default_factory=dict)

    async def create_draft(
        self,
        *,
        prompt_template_id: str,
        system_instructions: str,
        model: str,
        temperature: float | None,
    ) -> PromptVersion:
        existing = [v for v in self.versions.values() if v.prompt_template_id == prompt_template_id]
        next_number = (max(v.version_number for v in existing) + 1) if existing else 1
        version = PromptVersion(
            id=str(uuid.uuid4()),
            prompt_template_id=prompt_template_id,
            version_number=next_number,
            system_instructions=system_instructions,
            model=model,
            temperature=temperature,
            status=PromptVersionStatus.DRAFT,
            created_at=datetime.now(UTC),
            activated_at=None,
        )
        self.versions[version.id] = version
        return version

    async def get_by_id(self, version_id: str) -> PromptVersion | None:
        return self.versions.get(version_id)

    async def list_for_template(self, prompt_template_id: str) -> list[PromptVersion]:
        return [v for v in self.versions.values() if v.prompt_template_id == prompt_template_id]

    async def get_active(self, prompt_template_id: str) -> PromptVersion | None:
        return next(
            (
                v
                for v in self.versions.values()
                if v.prompt_template_id == prompt_template_id
                and v.status is PromptVersionStatus.ACTIVE
            ),
            None,
        )

    async def set_status(self, *, version_id: str, status: PromptVersionStatus) -> PromptVersion:
        current = self.versions[version_id]
        updated = PromptVersion(
            id=current.id,
            prompt_template_id=current.prompt_template_id,
            version_number=current.version_number,
            system_instructions=current.system_instructions,
            model=current.model,
            temperature=current.temperature,
            status=status,
            created_at=current.created_at,
            activated_at=(
                datetime.now(UTC) if status is PromptVersionStatus.ACTIVE else current.activated_at
            ),
        )
        self.versions[version_id] = updated
        return updated


@dataclass
class FakeGoldenExampleRepository:
    examples: dict[str, GoldenExample] = field(default_factory=dict)

    async def add(
        self,
        *,
        prompt_template_id: str,
        input: dict[str, object],
        rubric: str,
        expectation: dict[str, object],
    ) -> GoldenExample:
        from agentverse_api.orchestration_service.infrastructure.prompt_repository import (
            _expectation_to_dataclass,
        )

        rubric_type = RubricType(rubric)
        example = GoldenExample(
            id=str(uuid.uuid4()),
            prompt_template_id=prompt_template_id,
            input=input,
            rubric=rubric_type,
            expectation=_expectation_to_dataclass(rubric_type, expectation),
            created_at=datetime.now(UTC),
        )
        self.examples[example.id] = example
        return example

    async def list_for_template(self, prompt_template_id: str) -> list[GoldenExample]:
        return [e for e in self.examples.values() if e.prompt_template_id == prompt_template_id]


@dataclass
class FakeEvalRunRepository:
    runs: list[EvalRun] = field(default_factory=list)

    async def record(self, run: EvalRun) -> EvalRun:
        self.runs.append(run)
        return run

    async def latest_for_version(self, prompt_version_id: str) -> EvalRun | None:
        matching = [r for r in self.runs if r.prompt_version_id == prompt_version_id]
        if not matching:
            return None
        return max(matching, key=lambda r: r.started_at)
