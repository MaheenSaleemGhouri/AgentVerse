"""Repository port (Protocol) for `agent_runs`/`agent_run_steps`."""

from __future__ import annotations

from typing import Any, Protocol

from agentverse_api.orchestration_service.domain.run_entities import (
    AgentRun,
    AgentRunStep,
    RunStatus,
)


class AgentRunRepository(Protocol):
    async def create_run(
        self,
        *,
        workspace_id: str,
        agent_id: str,
        agent_version_id: str,
        input: dict[str, Any],
        idempotency_key: str | None,
    ) -> AgentRun: ...

    async def get_run_by_idempotency_key(
        self, *, workspace_id: str, idempotency_key: str
    ) -> AgentRun | None:
        """The lookup an idempotent resubmission hits — a match here
        means "return the original response," never create a second run.
        """
        ...

    async def get_run(self, *, workspace_id: str, run_id: str) -> AgentRun | None: ...

    async def update_status(
        self,
        *,
        run_id: str,
        status: RunStatus,
        cost_micro_usd: int | None = None,
        error_message: str | None = None,
    ) -> None: ...

    async def append_step(self, step: AgentRunStep) -> None: ...

    async def list_steps(self, *, run_id: str) -> list[AgentRunStep]: ...
