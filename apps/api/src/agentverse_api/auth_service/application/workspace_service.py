"""Workspace/membership use cases (docs/roadmap.md Phase 1 technical tasks)."""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.entities import Workspace, WorkspaceMember, WorkspaceSummary
from agentverse_api.auth_service.domain.exceptions import (
    LastOwnerError,
    UserAlreadyMemberError,
    WorkspaceSlugTakenError,
)
from agentverse_api.auth_service.domain.ports import WorkspaceRepository
from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.domain.slug import candidate_slugs


@dataclass(slots=True)
class WorkspaceService:
    workspaces: WorkspaceRepository
    audit: AuditService

    async def list_workspaces_for_user(self, user_id: str) -> list[WorkspaceSummary]:
        return await self.workspaces.list_for_user(user_id)

    async def create_workspace(self, *, name: str, owner_user_id: str) -> Workspace:
        slug = await self._resolve_available_slug(name)
        workspace = await self.workspaces.create_workspace(
            name=name, slug=slug, owner_user_id=owner_user_id
        )
        await self.audit.record(
            action="workspace.created",
            outcome="success",
            workspace_id=workspace.id,
            actor_user_id=owner_user_id,
            target=workspace.id,
        )
        return workspace

    async def _resolve_available_slug(self, name: str) -> str:
        for candidate in candidate_slugs(name):
            if not await self.workspaces.slug_exists(candidate):
                return candidate
        raise WorkspaceSlugTakenError(name)

    async def invite_member(
        self, *, workspace_id: str, inviter_user_id: str, invitee_user_id: str, role: Role
    ) -> WorkspaceMember:
        existing = await self.workspaces.get_membership(
            workspace_id=workspace_id, user_id=invitee_user_id
        )
        if existing is not None:
            raise UserAlreadyMemberError(invitee_user_id, workspace_id)

        member = await self.workspaces.add_member(
            workspace_id=workspace_id, user_id=invitee_user_id, role=role
        )
        await self.audit.record(
            action="member.invited",
            outcome="success",
            workspace_id=workspace_id,
            actor_user_id=inviter_user_id,
            target=invitee_user_id,
            metadata={"role": role.value},
        )
        return member

    async def change_member_role(
        self, *, workspace_id: str, actor_user_id: str, target_user_id: str, new_role: Role
    ) -> WorkspaceMember:
        current = await self.workspaces.get_membership(
            workspace_id=workspace_id, user_id=target_user_id
        )
        if (
            current is not None
            and current.role is Role.OWNER
            and new_role is not Role.OWNER
            and await self.workspaces.count_owners(workspace_id) <= 1
        ):
            raise LastOwnerError(workspace_id)

        member = await self.workspaces.update_member_role(
            workspace_id=workspace_id, user_id=target_user_id, role=new_role
        )
        await self.audit.record(
            action="member.role_changed",
            outcome="success",
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            target=target_user_id,
            metadata={"new_role": new_role.value},
        )
        return member

    async def remove_member(
        self, *, workspace_id: str, actor_user_id: str, target_user_id: str
    ) -> None:
        current = await self.workspaces.get_membership(
            workspace_id=workspace_id, user_id=target_user_id
        )
        if (
            current is not None
            and current.role is Role.OWNER
            and await self.workspaces.count_owners(workspace_id) <= 1
        ):
            raise LastOwnerError(workspace_id)

        await self.workspaces.remove_member(workspace_id=workspace_id, user_id=target_user_id)
        await self.audit.record(
            action="member.removed",
            outcome="success",
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            target=target_user_id,
        )

    async def list_members(self, workspace_id: str) -> list[WorkspaceMember]:
        return await self.workspaces.list_members(workspace_id)
