"""Repository port (Protocol) for `workflow_runs`/`workflow_node_runs`.
Submission and status-read only — actual node dispatch/advancement is
the worker's own `WorkflowRepositoryProtocol` (a separate, worker-local
protocol against the same tables, mirroring the `agent_runs`/
`AgentRunRepository` vs. worker `AgentRepositoryProtocol` split).
"""

from __future__ import annotations

from typing import Any, Protocol

from agentverse_api.orchestration_service.domain.workflow_entities import (
    WorkflowNodeRun,
    WorkflowRun,
)


class WorkflowRunRepository(Protocol):
    async def create_run(
        self,
        *,
        workspace_id: str,
        workflow_id: str,
        workflow_version_id: str,
        input: dict[str, Any],
        idempotency_key: str | None,
    ) -> WorkflowRun: ...

    async def get_run_by_idempotency_key(
        self, *, workflow_id: str, idempotency_key: str
    ) -> WorkflowRun | None: ...

    async def get_run(self, *, workspace_id: str, run_id: str) -> WorkflowRun | None: ...

    async def update_run_status(
        self, *, run_id: str, status: str, error_message: str | None = None
    ) -> None: ...

    async def list_node_runs(self, *, workflow_run_id: str) -> list[WorkflowNodeRun]: ...

    async def get_node_run(
        self, *, workflow_run_id: str, node_id: str
    ) -> WorkflowNodeRun | None: ...

    async def resolve_approval(
        self, *, node_run_id: str, decision: str, approved_by_user_id: str
    ) -> WorkflowNodeRun: ...
