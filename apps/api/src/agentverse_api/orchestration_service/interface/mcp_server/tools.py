"""The 7 tools AgentVerse's own MCP server exposes (docs/adr/0017) —
`list_agents`, `get_agent`, `run_agent`, `get_run_status`,
`list_workflows`, `get_workflow`, `run_workflow`. Each is a thin
adapter: resolve the caller's identity and role (`context.py`), check
authorization, delegate to the exact application function or repository
method the equivalent REST route already calls, audit the outcome.
Nothing here reimplements orchestration logic — the same "delegate,
never reimplement" principle Phase 10's workflow engine used for
Phase 9's primitives.

No arbitrary API exposure: this is a closed list, not a generic
database/API passthrough (CLAUDE.md §10's AI-specific threat-surface
rule extends naturally to an external-facing tool surface).
"""

from __future__ import annotations

import uuid
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.infrastructure.repositories import SqlAuditLogRepository
from agentverse_api.billing_service.application.quota_service import (
    QuotaExceededError,
)
from agentverse_api.billing_service.domain.plan import MeteredDimension
from agentverse_api.billing_service.interface.dependencies.services import get_quota_service
from agentverse_api.infrastructure.db import get_session_factory
from agentverse_api.orchestration_service.application.execute_workflow import (
    execute_workflow,
)
from agentverse_api.orchestration_service.application.run_agent import run_agent
from agentverse_api.orchestration_service.domain.run_exceptions import (
    AgentNotRunnableError,
    RunSubmissionConflictError,
)
from agentverse_api.orchestration_service.domain.workflow_exceptions import (
    WorkflowNotRunnableError,
)
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)
from agentverse_api.orchestration_service.infrastructure.repositories import (
    SqlAgentRepository,
    SqlAgentRunRepository,
)
from agentverse_api.orchestration_service.infrastructure.workflow_repository import (
    SqlWorkflowRepository,
)
from agentverse_api.orchestration_service.infrastructure.workflow_run_repository import (
    SqlWorkflowRunRepository,
)
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_lock_factory,
    get_redis_client,
)
from agentverse_api.orchestration_service.interface.mcp_server.context import (
    McpAuthorizationError,
    require_role,
    resolve_context,
)


def _agent_dict(agent: Any) -> dict[str, Any]:
    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "status": agent.status.value,
        "published_version_id": agent.published_version_id,
        "created_at": agent.created_at.isoformat(),
        "updated_at": agent.updated_at.isoformat(),
    }


def _workflow_dict(workflow: Any) -> dict[str, Any]:
    return {
        "id": workflow.id,
        "name": workflow.name,
        "description": workflow.description,
        "status": workflow.status.value,
        "published_version_id": workflow.published_version_id,
        "created_at": workflow.created_at.isoformat(),
        "updated_at": workflow.updated_at.isoformat(),
    }


def _run_dict(run: Any, *, run_type: str, id_field: str) -> dict[str, Any]:
    return {
        "id": run.id,
        id_field: getattr(run, id_field),
        "run_type": run_type,
        "status": run.status.value,
        "idempotency_key": run.idempotency_key,
        "cost_micro_usd": run.cost_micro_usd,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat(),
    }


async def _audit(
    session: Any, *, action: str, resolved: Any, outcome: str, target: str | None
) -> None:
    audit = AuditService(audit_logs=SqlAuditLogRepository(session))
    await audit.record(
        action=action,
        outcome=outcome,
        workspace_id=resolved.workspace_id,
        actor_user_id=resolved.user_id,
        target=target,
        metadata={"mcp_client_id": resolved.api_key_id},
    )
    await session.commit()


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_agents(ctx: Context[Any, Any, Any]) -> list[dict[str, Any]]:
        """List every agent in the caller's workspace."""
        resolved = resolve_context(ctx)
        session_factory = get_session_factory()
        async with session_factory() as session:
            require_role(resolved, Role.VIEWER)
            repo = SqlAgentRepository(session)
            agents = await repo.list_agents(workspace_id=resolved.workspace_id)
            await _audit(
                session,
                action="mcp_server.tool_executed",
                resolved=resolved,
                outcome="success",
                target="list_agents",
            )
            return [_agent_dict(a) for a in agents]

    @mcp.tool()
    async def get_agent(ctx: Context[Any, Any, Any], agent_id: str) -> dict[str, Any]:
        """Get one agent by id."""
        resolved = resolve_context(ctx)
        session_factory = get_session_factory()
        async with session_factory() as session:
            require_role(resolved, Role.VIEWER)
            repo = SqlAgentRepository(session)
            agent = await repo.get_agent(workspace_id=resolved.workspace_id, agent_id=agent_id)
            if agent is None:
                await _audit(
                    session,
                    action="mcp_server.tool_executed",
                    resolved=resolved,
                    outcome="not_found",
                    target=agent_id,
                )
                raise ValueError(f"No agent {agent_id!r} in this workspace")
            await _audit(
                session,
                action="mcp_server.tool_executed",
                resolved=resolved,
                outcome="success",
                target=agent_id,
            )
            return _agent_dict(agent)

    @mcp.tool()
    async def run_agent_tool(
        ctx: Context[Any, Any, Any],
        agent_id: str,
        input: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Run a published agent. `idempotency_key` defaults to a fresh
        one per call — pass your own to make a retried call safe.
        """
        resolved = resolve_context(ctx)
        session_factory = get_session_factory()
        async with session_factory() as session:
            try:
                require_role(resolved, Role.MEMBER)
            except McpAuthorizationError:
                await _audit(
                    session,
                    action="mcp_server.tool_denied",
                    resolved=resolved,
                    outcome="denied",
                    target=agent_id,
                )
                raise

            quota = get_quota_service(session)
            try:
                await quota.enforce(
                    workspace_id=resolved.workspace_id, dimension=MeteredDimension.AGENT_RUNS
                )
            except QuotaExceededError as exc:
                await _audit(
                    session,
                    action="mcp_server.tool_denied",
                    resolved=resolved,
                    outcome="quota_exceeded",
                    target=agent_id,
                )
                raise ValueError(f"Run quota exceeded: {exc}") from exc

            agent_repo = SqlAgentRepository(session)
            run_repo = SqlAgentRunRepository(session)
            producer = JobQueueProducer(get_redis_client(), stream="queue:jobs")
            lock_factory = get_lock_factory()
            try:
                run = await run_agent(
                    workspace_id=resolved.workspace_id,
                    agent_id=agent_id,
                    input=input,
                    idempotency_key=idempotency_key or str(uuid.uuid4()),
                    agent_repo=agent_repo,
                    run_repo=run_repo,
                    producer=producer,
                    lock_factory=lock_factory,
                )
            except AgentNotRunnableError as exc:
                await _audit(
                    session,
                    action="mcp_server.tool_executed",
                    resolved=resolved,
                    outcome="error",
                    target=agent_id,
                )
                raise ValueError("Agent has no published version to run") from exc
            except RunSubmissionConflictError as exc:
                raise ValueError(
                    "Could not confirm run submission — retry with the same idempotency_key"
                ) from exc

            await _audit(
                session,
                action="mcp_server.tool_executed",
                resolved=resolved,
                outcome="success",
                target=run.id,
            )
            return _run_dict(run, run_type="agent", id_field="agent_id")

    @mcp.tool()
    async def get_run_status(ctx: Context[Any, Any, Any], run_id: str) -> dict[str, Any]:
        """Get the status of a run — either an agent run or a workflow
        run, whichever `run_id` refers to.
        """
        resolved = resolve_context(ctx)
        session_factory = get_session_factory()
        async with session_factory() as session:
            require_role(resolved, Role.VIEWER)
            agent_run = await SqlAgentRunRepository(session).get_run(
                workspace_id=resolved.workspace_id, run_id=run_id
            )
            if agent_run is not None:
                await _audit(
                    session,
                    action="mcp_server.tool_executed",
                    resolved=resolved,
                    outcome="success",
                    target=run_id,
                )
                return _run_dict(agent_run, run_type="agent", id_field="agent_id")

            workflow_run = await SqlWorkflowRunRepository(session).get_run(
                workspace_id=resolved.workspace_id, run_id=run_id
            )
            if workflow_run is not None:
                await _audit(
                    session,
                    action="mcp_server.tool_executed",
                    resolved=resolved,
                    outcome="success",
                    target=run_id,
                )
                return _run_dict(workflow_run, run_type="workflow", id_field="workflow_id")

            await _audit(
                session,
                action="mcp_server.tool_executed",
                resolved=resolved,
                outcome="not_found",
                target=run_id,
            )
            raise ValueError(f"No run {run_id!r} in this workspace")

    @mcp.tool()
    async def list_workflows(ctx: Context[Any, Any, Any]) -> list[dict[str, Any]]:
        """List every workflow in the caller's workspace."""
        resolved = resolve_context(ctx)
        session_factory = get_session_factory()
        async with session_factory() as session:
            require_role(resolved, Role.VIEWER)
            repo = SqlWorkflowRepository(session)
            workflows = await repo.list_workflows(workspace_id=resolved.workspace_id)
            await _audit(
                session,
                action="mcp_server.tool_executed",
                resolved=resolved,
                outcome="success",
                target="list_workflows",
            )
            return [_workflow_dict(w) for w in workflows]

    @mcp.tool()
    async def get_workflow(ctx: Context[Any, Any, Any], workflow_id: str) -> dict[str, Any]:
        """Get one workflow by id."""
        resolved = resolve_context(ctx)
        session_factory = get_session_factory()
        async with session_factory() as session:
            require_role(resolved, Role.VIEWER)
            repo = SqlWorkflowRepository(session)
            workflow = await repo.get_workflow(
                workspace_id=resolved.workspace_id, workflow_id=workflow_id
            )
            if workflow is None:
                await _audit(
                    session,
                    action="mcp_server.tool_executed",
                    resolved=resolved,
                    outcome="not_found",
                    target=workflow_id,
                )
                raise ValueError(f"No workflow {workflow_id!r} in this workspace")
            await _audit(
                session,
                action="mcp_server.tool_executed",
                resolved=resolved,
                outcome="success",
                target=workflow_id,
            )
            return _workflow_dict(workflow)

    @mcp.tool()
    async def run_workflow(
        ctx: Context[Any, Any, Any],
        workflow_id: str,
        input: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Run a published workflow's DAG from its start node(s)."""
        resolved = resolve_context(ctx)
        session_factory = get_session_factory()
        async with session_factory() as session:
            try:
                require_role(resolved, Role.MEMBER)
            except McpAuthorizationError:
                await _audit(
                    session,
                    action="mcp_server.tool_denied",
                    resolved=resolved,
                    outcome="denied",
                    target=workflow_id,
                )
                raise

            quota = get_quota_service(session)
            try:
                await quota.enforce(
                    workspace_id=resolved.workspace_id,
                    dimension=MeteredDimension.WORKFLOW_EXECUTIONS,
                )
            except QuotaExceededError as exc:
                await _audit(
                    session,
                    action="mcp_server.tool_denied",
                    resolved=resolved,
                    outcome="quota_exceeded",
                    target=workflow_id,
                )
                raise ValueError(f"Run quota exceeded: {exc}") from exc

            workflow_repo = SqlWorkflowRepository(session)
            run_repo = SqlWorkflowRunRepository(session)
            producer = JobQueueProducer(get_redis_client(), stream="queue:jobs")
            lock_factory = get_lock_factory()
            try:
                run = await execute_workflow(
                    workspace_id=resolved.workspace_id,
                    workflow_id=workflow_id,
                    input=input,
                    idempotency_key=idempotency_key or str(uuid.uuid4()),
                    workflow_repo=workflow_repo,
                    run_repo=run_repo,
                    producer=producer,
                    lock_factory=lock_factory,
                )
            except WorkflowNotRunnableError as exc:
                await _audit(
                    session,
                    action="mcp_server.tool_executed",
                    resolved=resolved,
                    outcome="error",
                    target=workflow_id,
                )
                raise ValueError("Workflow has no published version with a start node") from exc
            except RunSubmissionConflictError as exc:
                raise ValueError(
                    "Could not confirm run submission — retry with the same idempotency_key"
                ) from exc

            await _audit(
                session,
                action="mcp_server.tool_executed",
                resolved=resolved,
                outcome="success",
                target=run.id,
            )
            return _run_dict(run, run_type="workflow", id_field="workflow_id")
