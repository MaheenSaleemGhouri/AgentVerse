"""Authoring surface for prompt templates/versions/golden examples —
the CRUD half of Phase 8's registry. Promotion and evaluation are
deliberately separate modules (`promote_prompt_version.py`,
`eval_harness/regression_runner.py`): each is a distinct use case with
its own failure modes, and folding all three into one service would
blur exactly the "CI-style gate" boundary the roadmap names.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_api.orchestration_service.domain.golden_dataset import GoldenExample, RubricType
from agentverse_api.orchestration_service.domain.ports.prompt_repository import (
    GoldenExampleRepository,
    PromptTemplateRepository,
    PromptVersionRepository,
)
from agentverse_api.orchestration_service.domain.prompt import PromptTemplate, PromptVersion


class PromptTemplateNotFoundError(Exception):
    """Maps to HTTP 404."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(f"No prompt template named {slug!r}")


class SlugTakenError(Exception):
    """Maps to HTTP 409."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(f"Prompt template slug {slug!r} is already in use")


@dataclass(slots=True)
class PromptTemplateService:
    templates: PromptTemplateRepository
    versions: PromptVersionRepository
    golden_examples: GoldenExampleRepository

    async def create_template(
        self, *, slug: str, name: str, description: str
    ) -> PromptTemplate:
        if await self.templates.get_by_slug(slug) is not None:
            raise SlugTakenError(slug)
        return await self.templates.create(slug=slug, name=name, description=description)

    async def create_draft_version(
        self,
        *,
        slug: str,
        system_instructions: str,
        model: str,
        temperature: float | None = None,
    ) -> PromptVersion:
        template = await self._require(slug)
        return await self.versions.create_draft(
            prompt_template_id=template.id,
            system_instructions=system_instructions,
            model=model,
            temperature=temperature,
        )

    async def add_golden_example(
        self,
        *,
        slug: str,
        input: dict[str, object],
        rubric: RubricType,
        expectation: dict[str, object],
    ) -> GoldenExample:
        template = await self._require(slug)
        return await self.golden_examples.add(
            prompt_template_id=template.id,
            input=input,
            rubric=rubric.value,
            expectation=expectation,
        )

    async def list_versions(self, slug: str) -> list[PromptVersion]:
        template = await self._require(slug)
        return await self.versions.list_for_template(template.id)

    async def get_active_version(self, slug: str) -> PromptVersion | None:
        """What a real caller (an agent, a workflow node) resolves a
        first-party prompt to at run time — never a slug/version pair
        hand-picked per call site, so a promotion takes effect for
        every consumer at once.
        """
        template = await self._require(slug)
        return await self.versions.get_active(template.id)

    async def list_templates(self) -> list[PromptTemplate]:
        return await self.templates.list_all()

    async def _require(self, slug: str) -> PromptTemplate:
        template = await self.templates.get_by_slug(slug)
        if template is None:
            raise PromptTemplateNotFoundError(slug)
        return template
