"""The tools AgentVerse's own MCP server exposes (docs/adr/0017,
docs/adr/0020) — the original 7 (`list_agents`, `get_agent`, `run_agent`,
`get_run_status`, `list_workflows`, `get_workflow`, `run_workflow`) plus
Phase 13's 5 support/commerce tools for the NovaCart Customer Support
Agent (`create_support_ticket`, `escalate_to_human`, `lookup_order`,
`check_shipping_status`, `request_return`). Each is a thin adapter:
resolve the caller's identity and role (`context.py`), check
authorization, delegate to the exact application function or repository
method the equivalent REST route already calls, audit the outcome.
Nothing here reimplements orchestration logic — the same "delegate,
never reimplement" principle Phase 10's workflow engine used for
Phase 9's primitives.

No arbitrary API exposure: this is a closed list, not a generic
database/API passthrough (CLAUDE.md §10's AI-specific threat-surface
rule extends naturally to an external-facing tool surface). Growing the
list from 7 to 12 is a recorded decision (ADR-0020), not scope creep —
it is still closed, and a caller's *own* agent additionally never sees
more of it than its `permissions.allowed_tools` grant names (ADR-0020's
self-install pattern), independent of what its credential's role would
otherwise permit.
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
from agentverse_api.orchestration_service.domain.integration_entities import InstallStatus
from agentverse_api.orchestration_service.domain.run_exceptions import (
    AgentNotRunnableError,
    RunSubmissionConflictError,
)
from agentverse_api.orchestration_service.domain.workflow_exceptions import (
    WorkflowNotRunnableError,
)
from agentverse_api.orchestration_service.infrastructure.integration_repository import (
    SqlIntegrationRepository,
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
from agentverse_api.support_service.application.support_ticket_service import (
    MAX_BODY_LENGTH,
    SupportTicketService,
)
from agentverse_api.support_service.infrastructure.repositories import (
    SqlSupportTicketRepository,
)

#: Cap on the free-text `subject`/`reason` fields these tools accept —
#: same reasoning as `MAX_BODY_LENGTH`: bounding prompt-injection blast
#: radius and cost on every free-text field that reaches an LLM prompt
#: (CLAUDE.md §7), not because a real subject line is ever this long.
MAX_SUBJECT_LENGTH = 200


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


def _ticket_dict(ticket: Any) -> dict[str, Any]:
    """Only what Section 7 (spec) allows back to the model: never the
    ticket body, never `created_by_user_id`, never anything beyond what
    a customer-facing agent should relay.
    """
    return {
        "ticket_id": ticket.id,
        "status": ticket.status.value,
        "category": ticket.category,
        "priority": ticket.priority,
        "created_at": ticket.created_at.isoformat(),
    }


def _support_ticket_service(session: Any) -> SupportTicketService:
    """Builds the full service even though these tools only call
    `create_ticket_direct` — the other four collaborators are the exact
    objects `run_agent_tool` above already constructs from the same
    session, so this adds no new wiring, just reuses it for a second
    call site.
    """
    return SupportTicketService(
        tickets=SqlSupportTicketRepository(session),
        agent_repo=SqlAgentRepository(session),
        run_repo=SqlAgentRunRepository(session),
        producer=JobQueueProducer(get_redis_client(), stream="queue:jobs"),
        lock_factory=get_lock_factory(),
    )


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

    # --- Phase 13: NovaCart support/commerce tools (ADR-0020) ------------

    @mcp.tool()
    async def create_support_ticket(
        ctx: Context[Any, Any, Any],
        subject: str,
        body: str,
        category: str | None = None,
        priority: str | None = None,
    ) -> dict[str, Any]:
        """Open a support ticket for a customer issue that needs human
        follow-up or a recorded case. `category`/`priority` are your own
        classification of the issue (free text — e.g. "billing"/"urgent")
        based on the conversation so far; both are optional.
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
                    target="create_support_ticket",
                )
                raise

            ticket = await _support_ticket_service(session).create_ticket_direct(
                workspace_id=resolved.workspace_id,
                subject=subject[:MAX_SUBJECT_LENGTH],
                body=body[:MAX_BODY_LENGTH],
                created_by_user_id=resolved.user_id,
                category=category,
                priority=priority,
            )
            await _audit(
                session,
                action="mcp_server.tool_executed",
                resolved=resolved,
                outcome="success",
                target=ticket.id,
            )
            return _ticket_dict(ticket)

    @mcp.tool()
    async def escalate_to_human(
        ctx: Context[Any, Any, Any],
        reason: str,
        summary: str,
        priority: str | None = None,
    ) -> dict[str, Any]:
        """Escalate to a human support representative — for refund
        disputes, account/security issues, unclear policy exceptions,
        anything the knowledge base doesn't cover, or a request that
        needs privileged action. This only records the escalation as a
        ticket for a human to act on; it never performs a sensitive
        action itself.
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
                    target="escalate_to_human",
                )
                raise

            ticket = await _support_ticket_service(session).create_ticket_direct(
                workspace_id=resolved.workspace_id,
                subject=f"Escalation: {reason}"[:MAX_SUBJECT_LENGTH],
                body=summary[:MAX_BODY_LENGTH],
                created_by_user_id=resolved.user_id,
                category="escalation",
                priority=priority or "urgent",
            )
            await _audit(
                session,
                action="mcp_server.tool_executed",
                resolved=resolved,
                outcome="success",
                target=ticket.id,
            )
            return _ticket_dict(ticket)

    async def _commerce_integration_available(session: Any, workspace_id: str) -> bool:
        """Whether *any* live, active MCP integration is installed for
        this workspace.

        Deliberately not narrowed to "the right kind" of integration
        (e.g. Shopify specifically) — AgentVerse has no live commerce
        integration to develop or test that distinction against today
        (ADR-0020), and guessing at a filter nothing exercises would be
        exactly the kind of untested code this constitution warns
        against. An install existing is necessary but not sufficient for
        a real order lookup to work; see the tools' own docstrings.
        """
        installs = await SqlIntegrationRepository(session).list_installed(
            workspace_id=workspace_id
        )
        return any(install.status is InstallStatus.ACTIVE for install in installs)

    @mcp.tool()
    async def lookup_order(ctx: Context[Any, Any, Any], order_number: str) -> dict[str, Any]:
        """Look up an order's status. Only works when a real commerce
        integration (e.g. Shopify) is installed and configured for this
        workspace — AgentVerse stores no order data of its own. Returns
        `{"available": false, ...}` rather than inventing an order when
        no such integration is connected; never guess or fabricate an
        order status.
        """
        resolved = resolve_context(ctx)
        session_factory = get_session_factory()
        async with session_factory() as session:
            require_role(resolved, Role.VIEWER)
            available = await _commerce_integration_available(session, resolved.workspace_id)
            result = (
                {
                    "available": False,
                    "reason": (
                        "A commerce integration is installed for this workspace, but live "
                        "order lookup through it is not yet wired (Phase 13 follow-up)."
                    ),
                }
                if available
                else {
                    "available": False,
                    "reason": "No commerce integration is installed for this workspace.",
                }
            )
            await _audit(
                session,
                action="mcp_server.tool_executed",
                resolved=resolved,
                outcome="unavailable",
                target=order_number,
            )
            return result

    @mcp.tool()
    async def check_shipping_status(
        ctx: Context[Any, Any, Any], order_number: str
    ) -> dict[str, Any]:
        """Check an order's shipping/tracking status. Same integration
        requirement as `lookup_order` — never fabricates a carrier,
        tracking status, or delivery date when no integration is
        connected.
        """
        resolved = resolve_context(ctx)
        session_factory = get_session_factory()
        async with session_factory() as session:
            require_role(resolved, Role.VIEWER)
            available = await _commerce_integration_available(session, resolved.workspace_id)
            result = (
                {
                    "available": False,
                    "reason": (
                        "A commerce integration is installed for this workspace, but live "
                        "shipping lookup through it is not yet wired (Phase 13 follow-up)."
                    ),
                }
                if available
                else {
                    "available": False,
                    "reason": "No commerce integration is installed for this workspace.",
                }
            )
            await _audit(
                session,
                action="mcp_server.tool_executed",
                resolved=resolved,
                outcome="unavailable",
                target=order_number,
            )
            return result

    @mcp.tool()
    async def request_return(
        ctx: Context[Any, Any, Any], order_number: str, reason: str
    ) -> dict[str, Any]:
        """Request a return for an order. This never processes a return
        automatically — every return request is routed to a human for
        approval, regardless of whether a commerce integration is
        connected, so a model cannot authorize a refund/return on its
        own judgment (Section 17's approval-required rule).
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
                    target=order_number,
                )
                raise

            ticket = await _support_ticket_service(session).create_ticket_direct(
                workspace_id=resolved.workspace_id,
                subject=f"Return request: order {order_number}"[:MAX_SUBJECT_LENGTH],
                body=reason[:MAX_BODY_LENGTH],
                created_by_user_id=resolved.user_id,
                category="return-request",
                priority="normal",
            )
            await _audit(
                session,
                action="mcp_server.tool_executed",
                resolved=resolved,
                outcome="routed_for_approval",
                target=ticket.id,
            )
            return {
                "available": True,
                "approval_required": True,
                **_ticket_dict(ticket),
            }
