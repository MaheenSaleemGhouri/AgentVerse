"""Tenant-defined roles, layered on the seven built-in tiers.

The built-in hierarchy (`domain/role.py`) and its permission matrix
(`domain/permission.py`) cover the common shapes. This service exists for
the case they don't: an organization that wants "Support Engineer" to be
a member who may also read audit logs, without promoting them to analyst
and handing over billing visibility they shouldn't have.

Two invariants hold every custom role in line with the rest of the model:

- **A custom role always names a built-in base tier.** That keeps it
  rankable, so every route still gated on a minimum role via
  `require_role` keeps working with no awareness that custom roles exist.
- **Grants are additive only.** There is no subtract. A role that removed
  an inherited capability would make the hierarchy non-monotonic, and a
  member could then fail a check their nominal tier says they pass.

A custom role can never exceed its base tier's *rank*, but it can hold
permissions from higher tiers — that is the entire point. What it cannot
do is change what `satisfies()` answers, which is why assigning one never
touches `workspace_members.role`.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.entities import CustomRole
from agentverse_api.auth_service.domain.exceptions import (
    CustomRoleNotFoundError,
    InvalidPermissionError,
)
from agentverse_api.auth_service.domain.permission import Permission
from agentverse_api.auth_service.domain.ports import CustomRoleRepository
from agentverse_api.auth_service.domain.role import Role


def validate_permissions(values: list[str]) -> list[str]:
    """Rejects any grant that isn't a real `Permission`.

    Raised rather than filtered: an admin who mistypes a permission must
    be told, not left believing a grant took effect. Pure, so it is
    unit-testable without a database.
    """
    known = {p.value for p in Permission}
    for value in values:
        if value not in known:
            raise InvalidPermissionError(value)
    # Deduplicated and ordered so the stored set is canonical — two
    # requests differing only in ordering produce the same role.
    return sorted(set(values))


@dataclass(slots=True)
class RbacService:
    roles: CustomRoleRepository
    audit: AuditService

    async def create_role(
        self,
        *,
        workspace_id: str,
        name: str,
        description: str | None,
        base_role: Role,
        permissions: list[str],
        actor_user_id: str,
    ) -> CustomRole:
        validated = validate_permissions(permissions)
        role = await self.roles.create(
            workspace_id=workspace_id,
            name=name,
            description=description,
            base_role=base_role,
            permissions=validated,
            created_by_user_id=actor_user_id,
        )
        await self.audit.record(
            action="role.created",
            outcome="success",
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            target=role.id,
            metadata={
                "name": name,
                "base_role": base_role.value,
                "permissions": ",".join(validated),
            },
        )
        return role

    async def update_role(
        self,
        *,
        workspace_id: str,
        role_id: str,
        name: str | None,
        description: str | None,
        base_role: Role | None,
        permissions: list[str] | None,
        actor_user_id: str,
    ) -> CustomRole:
        validated = None if permissions is None else validate_permissions(permissions)
        role = await self.roles.update(
            workspace_id=workspace_id,
            role_id=role_id,
            name=name,
            description=description,
            base_role=base_role,
            permissions=validated,
        )
        await self.audit.record(
            action="role.updated",
            outcome="success",
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            target=role_id,
            metadata={
                "base_role": role.base_role.value,
                "permissions": ",".join(role.permissions),
            },
        )
        return role

    async def delete_role(self, *, workspace_id: str, role_id: str, actor_user_id: str) -> None:
        await self.roles.delete(workspace_id=workspace_id, role_id=role_id)
        # Members holding this role fall back to their base tier rather
        # than losing access: `workspace_members.custom_role_id` is
        # ON DELETE SET NULL, and `role` was never overwritten.
        await self.audit.record(
            action="role.deleted",
            outcome="success",
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            target=role_id,
        )

    async def get_role(self, *, workspace_id: str, role_id: str) -> CustomRole:
        role = await self.roles.get(workspace_id=workspace_id, role_id=role_id)
        if role is None:
            raise CustomRoleNotFoundError(role_id)
        return role

    async def list_roles(self, workspace_id: str) -> list[CustomRole]:
        return await self.roles.list_for_workspace(workspace_id)
