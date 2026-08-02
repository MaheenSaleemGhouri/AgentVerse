"""Workspace IP restriction (Increment 7.4), composed as a *third*
check alongside `get_current_workspace`/`require_role` — never replacing
either. A route that doesn't depend on this is completely unaffected,
and a workspace with no allowlist rows is unrestricted, so every
pre-existing workspace behaves exactly as before.

Mirrors `require_role.py`'s audit-on-denial contract (`ip.denied`, with
an explicit commit so the denial write survives the 403 that follows).
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.application.ip_allowlist_service import IpAllowlistService
from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.infrastructure.repositories import (
    SqlAuditLogRepository,
    SqlIpAllowlistRepository,
)
from agentverse_api.auth_service.interface.dependencies.get_current_workspace import (
    get_current_workspace,
)
from agentverse_api.infrastructure.db import get_db_session


def client_ip_of(request: Request) -> str | None:
    """The caller's IP as this deployment can best determine it.

    `X-Forwarded-For`'s *first* entry is the original client when a
    trusted proxy appends to the header. This is only as trustworthy as
    the proxy in front of the app: a deployment that exposes the API
    directly to the internet must not rely on it, because a client can
    forge the header. Documented here rather than silently assumed —
    treating a forgeable header as authoritative is exactly how an IP
    allowlist becomes decorative.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else None


async def enforce_ip_allowlist(
    request: Request,
    context: WorkspaceContext = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    audit = AuditService(audit_logs=SqlAuditLogRepository(session))
    service = IpAllowlistService(entries=SqlIpAllowlistRepository(session), audit=audit)

    client_ip = client_ip_of(request)
    if await service.is_allowed(workspace_id=context.workspace_id, client_ip=client_ip):
        return

    await audit.record(
        action="ip.denied",
        outcome="denied",
        workspace_id=context.workspace_id,
        actor_user_id=context.user_id,
        metadata={"client_ip": client_ip or "unknown"},
    )
    # Commit explicitly — see `require_role.py`'s identical comment.
    await session.commit()

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Your IP address is not allowed for this workspace",
    )
