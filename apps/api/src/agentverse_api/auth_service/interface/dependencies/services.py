"""Assembles application-layer services from a request-scoped DB session.

Thin composition root for this bounded context — routes depend on these
factories, never construct a repository or service themselves.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.application.api_key_service import ApiKeyService
from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.application.workspace_service import WorkspaceService
from agentverse_api.auth_service.infrastructure.repositories import (
    SqlApiKeyRepository,
    SqlAuditLogRepository,
    SqlWorkspaceRepository,
)
from agentverse_api.infrastructure.db import get_db_session


def get_workspace_service(session: AsyncSession = Depends(get_db_session)) -> WorkspaceService:
    audit = AuditService(audit_logs=SqlAuditLogRepository(session))
    return WorkspaceService(workspaces=SqlWorkspaceRepository(session), audit=audit)


def get_api_key_service(session: AsyncSession = Depends(get_db_session)) -> ApiKeyService:
    audit = AuditService(audit_logs=SqlAuditLogRepository(session))
    return ApiKeyService(api_keys=SqlApiKeyRepository(session), audit=audit)
