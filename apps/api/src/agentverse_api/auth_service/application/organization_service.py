"""Organization/membership use cases — mirrors `workspace_service.py`
structurally (ADR-0011). Attaching/detaching a workspace never touches
`workspace_members`; the workspace's own RBAC is untouched by anything
in this file.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.entities import (
    MemberPresence,
    Organization,
    OrganizationMember,
    OrganizationStats,
    OrganizationSummary,
    Workspace,
)
from agentverse_api.auth_service.domain.exceptions import (
    LastOrgOwnerError,
    OrganizationSlugTakenError,
    UserAlreadyOrgMemberError,
)
from agentverse_api.auth_service.domain.ports import OrganizationRepository
from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.domain.slug import candidate_slugs


@dataclass(slots=True)
class OrganizationService:
    organizations: OrganizationRepository
    audit: AuditService

    async def list_organizations_for_user(self, user_id: str) -> list[OrganizationSummary]:
        return await self.organizations.list_for_user(user_id)

    async def create_organization(self, *, name: str, owner_user_id: str) -> Organization:
        slug = await self._resolve_available_slug(name)
        organization = await self.organizations.create_organization(
            name=name, slug=slug, owner_user_id=owner_user_id
        )
        await self.audit.record(
            action="organization.created",
            outcome="success",
            organization_id=organization.id,
            actor_user_id=owner_user_id,
            target=organization.id,
        )
        return organization

    async def _resolve_available_slug(self, name: str) -> str:
        for candidate in candidate_slugs(name):
            if not await self.organizations.slug_exists(candidate):
                return candidate
        raise OrganizationSlugTakenError(name)

    async def rename_organization(
        self, *, organization_id: str, actor_user_id: str, name: str
    ) -> Organization:
        organization = await self.organizations.rename_organization(
            organization_id=organization_id, name=name
        )
        await self.audit.record(
            action="organization.renamed",
            outcome="success",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            target=organization_id,
            metadata={"name": name},
        )
        return organization

    async def delete_organization(self, *, organization_id: str, actor_user_id: str) -> None:
        # Audit first, delete second: `audit_logs.organization_id` is a
        # real FK, so recording after the delete would violate it (the row
        # it references would already be gone). The workspace-attached
        # `audit_logs.workspace_id` deletion event has the same ordering
        # constraint for the same reason.
        await self.audit.record(
            action="organization.deleted",
            outcome="success",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            target=organization_id,
        )
        # `workspaces.organization_id` has `ON DELETE SET NULL` — deleting
        # the row below detaches every attached workspace at the database
        # level. No application-layer detach step is needed or correct to
        # add (ADR-0011): this method must never touch `workspace_members`.
        await self.organizations.delete_organization(organization_id)

    async def invite_member(
        self, *, organization_id: str, inviter_user_id: str, invitee_user_id: str, role: Role
    ) -> OrganizationMember:
        existing = await self.organizations.get_membership(
            organization_id=organization_id, user_id=invitee_user_id
        )
        if existing is not None:
            raise UserAlreadyOrgMemberError(invitee_user_id, organization_id)

        member = await self.organizations.add_member(
            organization_id=organization_id, user_id=invitee_user_id, role=role
        )
        await self.audit.record(
            action="organization_member.invited",
            outcome="success",
            organization_id=organization_id,
            actor_user_id=inviter_user_id,
            target=invitee_user_id,
            metadata={"role": role.value},
        )
        return member

    async def change_member_role(
        self, *, organization_id: str, actor_user_id: str, target_user_id: str, new_role: Role
    ) -> OrganizationMember:
        current = await self.organizations.get_membership(
            organization_id=organization_id, user_id=target_user_id
        )
        if (
            current is not None
            and current.role is Role.OWNER
            and new_role is not Role.OWNER
            and await self.organizations.count_owners(organization_id) <= 1
        ):
            raise LastOrgOwnerError(organization_id)

        member = await self.organizations.update_member_role(
            organization_id=organization_id, user_id=target_user_id, role=new_role
        )
        await self.audit.record(
            action="organization_member.role_changed",
            outcome="success",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            target=target_user_id,
            metadata={"new_role": new_role.value},
        )
        return member

    async def suspend_member(
        self, *, organization_id: str, actor_user_id: str, target_user_id: str
    ) -> OrganizationMember:
        current = await self.organizations.get_membership(
            organization_id=organization_id, user_id=target_user_id
        )
        if (
            current is not None
            and current.role is Role.OWNER
            and await self.organizations.count_owners(organization_id) <= 1
        ):
            raise LastOrgOwnerError(organization_id)

        member = await self.organizations.suspend_member(
            organization_id=organization_id, user_id=target_user_id
        )
        await self.audit.record(
            action="organization_member.suspended",
            outcome="success",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            target=target_user_id,
        )
        return member

    async def reinstate_member(
        self, *, organization_id: str, actor_user_id: str, target_user_id: str
    ) -> OrganizationMember:
        member = await self.organizations.reinstate_member(
            organization_id=organization_id, user_id=target_user_id
        )
        await self.audit.record(
            action="organization_member.reinstated",
            outcome="success",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            target=target_user_id,
        )
        return member

    async def remove_member(
        self, *, organization_id: str, actor_user_id: str, target_user_id: str
    ) -> None:
        current = await self.organizations.get_membership(
            organization_id=organization_id, user_id=target_user_id
        )
        if (
            current is not None
            and current.role is Role.OWNER
            and await self.organizations.count_owners(organization_id) <= 1
        ):
            raise LastOrgOwnerError(organization_id)

        await self.organizations.remove_member(
            organization_id=organization_id, user_id=target_user_id
        )
        await self.audit.record(
            action="organization_member.removed",
            outcome="success",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            target=target_user_id,
        )

    async def list_members(self, organization_id: str) -> list[OrganizationMember]:
        return await self.organizations.list_members(organization_id)

    async def list_workspaces(self, organization_id: str) -> list[Workspace]:
        return await self.organizations.list_workspaces(organization_id)

    async def get_organization(self, organization_id: str) -> Organization | None:
        return await self.organizations.get_organization(organization_id)

    async def list_member_presence(self, organization_id: str) -> list[MemberPresence]:
        return await self.organizations.list_member_presence(organization_id)

    async def stats(self, organization_id: str) -> OrganizationStats:
        return await self.organizations.stats(organization_id)

    async def attach_workspace(
        self, *, organization_id: str, actor_user_id: str, workspace_id: str
    ) -> None:
        await self.organizations.attach_workspace(
            organization_id=organization_id, workspace_id=workspace_id
        )
        await self.audit.record(
            action="organization.workspace_attached",
            outcome="success",
            organization_id=organization_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            target=workspace_id,
        )

    async def detach_workspace(
        self, *, organization_id: str, actor_user_id: str, workspace_id: str
    ) -> None:
        await self.organizations.detach_workspace(workspace_id=workspace_id)
        await self.audit.record(
            action="organization.workspace_detached",
            outcome="success",
            organization_id=organization_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            target=workspace_id,
        )
