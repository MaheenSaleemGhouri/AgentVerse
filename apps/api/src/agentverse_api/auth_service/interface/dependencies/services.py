"""Assembles application-layer services from a request-scoped DB session.

Thin composition root for this bounded context — routes depend on these
factories, never construct a repository or service themselves.
"""

from __future__ import annotations

from agentverse_shared.security.envelope import CredentialVault
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.application.api_key_service import ApiKeyService
from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.application.invitation_service import InvitationService
from agentverse_api.auth_service.application.ip_allowlist_service import IpAllowlistService
from agentverse_api.auth_service.application.organization_service import OrganizationService
from agentverse_api.auth_service.application.resource_permission_service import (
    ResourcePermissionService,
)
from agentverse_api.auth_service.application.scim_service import ScimService
from agentverse_api.auth_service.application.sso_service import SsoService
from agentverse_api.auth_service.application.workspace_service import WorkspaceService
from agentverse_api.auth_service.application.workspace_settings_service import (
    WorkspaceSettingsService,
)
from agentverse_api.auth_service.infrastructure.email import LoggingEmailSender
from agentverse_api.auth_service.infrastructure.repositories import (
    SqlApiKeyRepository,
    SqlAuditLogRepository,
    SqlInvitationRepository,
    SqlIpAllowlistRepository,
    SqlOrganizationRepository,
    SqlResourcePermissionRepository,
    SqlScimRepository,
    SqlScimTokenRepository,
    SqlSsoConfigurationRepository,
    SqlUserLookupRepository,
    SqlWorkspaceRepository,
    SqlWorkspaceSettingsRepository,
)
from agentverse_api.infrastructure.config import get_settings
from agentverse_api.infrastructure.db import get_db_session
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_credential_vault,
)


def get_workspace_service(session: AsyncSession = Depends(get_db_session)) -> WorkspaceService:
    audit = AuditService(audit_logs=SqlAuditLogRepository(session))
    return WorkspaceService(workspaces=SqlWorkspaceRepository(session), audit=audit)


def get_organization_service(
    session: AsyncSession = Depends(get_db_session),
) -> OrganizationService:
    audit = AuditService(audit_logs=SqlAuditLogRepository(session))
    return OrganizationService(organizations=SqlOrganizationRepository(session), audit=audit)


def get_api_key_service(session: AsyncSession = Depends(get_db_session)) -> ApiKeyService:
    audit = AuditService(audit_logs=SqlAuditLogRepository(session))
    return ApiKeyService(api_keys=SqlApiKeyRepository(session), audit=audit)


def get_audit_service(session: AsyncSession = Depends(get_db_session)) -> AuditService:
    return AuditService(audit_logs=SqlAuditLogRepository(session))


def get_workspace_settings_service(
    session: AsyncSession = Depends(get_db_session),
) -> WorkspaceSettingsService:
    audit = AuditService(audit_logs=SqlAuditLogRepository(session))
    return WorkspaceSettingsService(settings=SqlWorkspaceSettingsRepository(session), audit=audit)


def get_invitation_service(
    session: AsyncSession = Depends(get_db_session),
) -> InvitationService:
    audit = AuditService(audit_logs=SqlAuditLogRepository(session))
    settings = get_settings()
    return InvitationService(
        invitations=SqlInvitationRepository(session),
        users=SqlUserLookupRepository(session),
        email_sender=LoggingEmailSender(),
        workspaces=WorkspaceService(workspaces=SqlWorkspaceRepository(session), audit=audit),
        organizations=OrganizationService(
            organizations=SqlOrganizationRepository(session), audit=audit
        ),
        audit=audit,
        web_public_url=settings.auth_public_url,
    )


def get_resource_permission_service(
    session: AsyncSession = Depends(get_db_session),
) -> ResourcePermissionService:
    audit = AuditService(audit_logs=SqlAuditLogRepository(session))
    return ResourcePermissionService(
        resource_permissions=SqlResourcePermissionRepository(session), audit=audit
    )


def get_ip_allowlist_service(
    session: AsyncSession = Depends(get_db_session),
) -> IpAllowlistService:
    audit = AuditService(audit_logs=SqlAuditLogRepository(session))
    return IpAllowlistService(entries=SqlIpAllowlistRepository(session), audit=audit)


def get_sso_service(
    session: AsyncSession = Depends(get_db_session),
    vault: CredentialVault = Depends(get_credential_vault),
) -> SsoService:
    audit = AuditService(audit_logs=SqlAuditLogRepository(session))
    return SsoService(
        configurations=SqlSsoConfigurationRepository(session), vault=vault, audit=audit
    )


def get_scim_service(
    session: AsyncSession = Depends(get_db_session),
) -> ScimService:
    audit = AuditService(audit_logs=SqlAuditLogRepository(session))
    return ScimService(
        tokens=SqlScimTokenRepository(session),
        directory=SqlScimRepository(session),
        audit=audit,
    )
