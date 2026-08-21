"""Repository ports (Protocols) for prompt templates/versions, golden
examples, and eval runs. `infrastructure/prompt_repository.py`
implements these against Postgres; tests implement them against
in-memory fakes (CLAUDE.md §5).
"""

from __future__ import annotations

from typing import Protocol

from agentverse_api.orchestration_service.domain.eval_run import EvalRun
from agentverse_api.orchestration_service.domain.golden_dataset import GoldenExample
from agentverse_api.orchestration_service.domain.prompt import (
    PromptTemplate,
    PromptVersion,
    PromptVersionStatus,
)


class PromptTemplateRepository(Protocol):
    async def create(self, *, slug: str, name: str, description: str) -> PromptTemplate: ...

    async def get_by_slug(self, slug: str) -> PromptTemplate | None: ...

    async def get_by_id(self, template_id: str) -> PromptTemplate | None: ...

    async def list_all(self) -> list[PromptTemplate]: ...


class PromptVersionRepository(Protocol):
    async def create_draft(
        self,
        *,
        prompt_template_id: str,
        system_instructions: str,
        model: str,
        temperature: float | None,
    ) -> PromptVersion:
        """`version_number` is assigned by the repository — one higher
        than the template's current latest, so callers never race on it.
        """
        ...

    async def get_by_id(self, version_id: str) -> PromptVersion | None: ...

    async def list_for_template(self, prompt_template_id: str) -> list[PromptVersion]: ...

    async def get_active(self, prompt_template_id: str) -> PromptVersion | None: ...

    async def set_status(
        self, *, version_id: str, status: PromptVersionStatus
    ) -> PromptVersion:
        """Sets `status`; sets `activated_at` to now when transitioning
        into `ACTIVE`, never otherwise. Does not itself validate the
        transition — `domain.prompt.assert_transition` is the single
        source of what's legal, called by every application-layer
        caller before this.
        """
        ...


class GoldenExampleRepository(Protocol):
    async def add(
        self,
        *,
        prompt_template_id: str,
        input: dict[str, object],
        rubric: str,
        expectation: dict[str, object],
    ) -> GoldenExample: ...

    async def list_for_template(self, prompt_template_id: str) -> list[GoldenExample]: ...


class EvalRunRepository(Protocol):
    async def record(self, run: EvalRun) -> EvalRun:
        """Persists a completed run — `regression_runner.py` builds the
        whole `EvalRun` (every example already scored) before calling
        this, so there is no partial/in-progress row to reconcile.
        """
        ...

    async def latest_for_version(self, prompt_version_id: str) -> EvalRun | None: ...
