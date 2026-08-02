"""Resource-scoped permission grants — orthogonal to the four base
workspace roles (see `domain.entities.ResourcePermission`'s docstring).
"""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.entities import ResourcePermission
from agentverse_api.auth_service.domain.ports import ResourcePermissionRepository

#: The only principal type this increment supports — see the domain
#: entity's docstring for why the column exists anyway.
_USER_PRINCIPAL_TYPE = "user"


@dataclass(slots=True)
class ResourcePermissionService:
    resource_permissions: ResourcePermissionRepository
    audit: AuditService

    async def grant(
        self,
        *,
        workspace_id: str,
        resource_type: str,
        resource_id: str,
        principal_id: str,
        permission: str,
        granted_by_user_id: str,
    ) -> ResourcePermission:
        grant = await self.resource_permissions.grant(
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
            principal_type=_USER_PRINCIPAL_TYPE,
            principal_id=principal_id,
            permission=permission,
            granted_by_user_id=granted_by_user_id,
        )
        await self.audit.record(
            action="resource_permission.granted",
            outcome="success",
            workspace_id=workspace_id,
            actor_user_id=granted_by_user_id,
            target=principal_id,
            metadata={
                "resource_type": resource_type,
                "resource_id": resource_id,
                "permission": permission,
            },
        )
        return grant

    async def revoke(
        self, *, workspace_id: str, permission_id: str, actor_user_id: str
    ) -> None:
        await self.resource_permissions.revoke_by_id(
            workspace_id=workspace_id, permission_id=permission_id
        )
        await self.audit.record(
            action="resource_permission.revoked",
            outcome="success",
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            target=permission_id,
        )

    async def list_for_workspace(self, workspace_id: str) -> list[ResourcePermission]:
        return await self.resource_permissions.list_for_workspace(workspace_id)
