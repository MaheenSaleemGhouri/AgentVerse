"""Gathers the facts the security score is computed from.

Lives in the interface layer, not the application layer, because it
reaches across four repositories that no single use case owns —
membership, IP allowlist, SSO, API keys — purely to assemble a read
model. Putting it in `SecurityService` would give that service
dependencies on half the bounded context just to answer one question.

The scoring itself stays a pure function in `domain.security`; this only
supplies its inputs.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_api.auth_service.domain.ports import (
    ApiKeyRepository,
    IpAllowlistRepository,
    PasswordPolicyRepository,
    SsoConfigurationRepository,
    WorkspaceRepository,
)


@dataclass(frozen=True, slots=True)
class PostureFacts:
    two_factor_enabled_members: int
    total_members: int
    ip_allowlist_configured: bool
    sso_enforced: bool
    password_policy_configured: bool
    non_expiring_api_keys: int


@dataclass(slots=True)
class SecurityPostureReader:
    workspaces: WorkspaceRepository
    ip_allowlist: IpAllowlistRepository
    sso: SsoConfigurationRepository
    policies: PasswordPolicyRepository
    api_keys: ApiKeyRepository

    async def gather(self, workspace_id: str) -> PostureFacts:
        enabled, total = await self.workspaces.count_two_factor_coverage(workspace_id)
        allowlist = await self.ip_allowlist.list_for_workspace(workspace_id)
        non_expiring = await self.api_keys.count_non_expiring(workspace_id)

        # SSO and password policy are organization-scoped, and a
        # workspace need not belong to one (ADR-0011 — the link is
        # optional). An unattached workspace simply cannot earn those
        # points; it is not an error, and it must not be scored as if
        # the controls were configured.
        sso_enforced = False
        policy_configured = False
        workspace = await self.workspaces.get_workspace(workspace_id)
        if workspace is not None and workspace.organization_id is not None:
            configs = await self.sso.list_for_organization(workspace.organization_id)
            sso_enforced = any(config.enabled for config in configs)
            policy_configured = await self.policies.get(workspace.organization_id) is not None

        return PostureFacts(
            two_factor_enabled_members=enabled,
            total_members=total,
            ip_allowlist_configured=len(allowlist) > 0,
            sso_enforced=sso_enforced,
            password_policy_configured=policy_configured,
            non_expiring_api_keys=non_expiring,
        )
