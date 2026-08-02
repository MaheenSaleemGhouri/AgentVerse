"""SCIM 2.0 provisioning, organization-scoped.

**Why this may create `users` rows when ADR-0005 says Better Auth owns
user creation.** SCIM exists precisely so the identity provider is the
source of truth for *who exists*. A SCIM-created row is an identity
shell — no `accounts` row, no password, no credential of any kind — so
it grants nothing on its own. The only way to sign into it is the
organization's SSO, which then finds the account by email instead of
JIT-creating it. Better Auth still owns every authentication path; this
owns only the directory.

**What SCIM can and cannot reach.** A token provisions organization
membership. It cannot grant workspace access, because organization
membership never implies workspace access (ADR-0006) — so SCIM Groups
are read-only, exposing the organization's workspaces as a directory
rather than as something an IdP can write into. Making Groups writable
would quietly invert that ADR from an identity provider's config page,
which is exactly the kind of change that should be a deliberate ADR
rather than a side effect of shipping SCIM.

**Deactivate vs delete.** SCIM's `active: false` suspends the
membership; `DELETE` removes it. Neither ever deletes the account: the
same person may belong to other organizations, and their runs and audit
entries reference the user row.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.entities import (
    ScimToken,
    ScimUser,
    Workspace,
)
from agentverse_api.auth_service.domain.ports import ScimRepository, ScimTokenRepository
from agentverse_api.auth_service.domain.role import Role

_TOKEN_PREFIX = "av_scim_"
_SECRET_BYTES = 32

#: SCIM-provisioned people join as members. Elevating someone to
#: admin/owner stays a deliberate in-product action — an IdP group
#: rename should never be able to hand out organization ownership.
DEFAULT_PROVISIONED_ROLE = Role.MEMBER


def _hash_token(plaintext: str) -> str:
    # Fast hash, same reasoning as `api_key_service`: the token is
    # already high-entropy, so Argon2id would be pure overhead.
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class IssuedScimToken:
    entity: ScimToken
    plaintext_token: str


@dataclass(slots=True)
class ScimService:
    tokens: ScimTokenRepository
    directory: ScimRepository
    audit: AuditService

    # --- token management (admin-facing) --------------------------------

    async def issue_token(
        self, *, organization_id: str, name: str, actor_user_id: str
    ) -> IssuedScimToken:
        secret = secrets.token_urlsafe(_SECRET_BYTES)
        plaintext = f"{_TOKEN_PREFIX}{secret}"
        entity = await self.tokens.create(
            organization_id=organization_id,
            name=name,
            token_prefix=plaintext[: len(_TOKEN_PREFIX) + 6],
            hashed_token=_hash_token(plaintext),
            created_by_user_id=actor_user_id,
        )
        await self.audit.record(
            action="scim_token.issued",
            outcome="success",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            target=entity.id,
            metadata={"name": name},
        )
        return IssuedScimToken(entity=entity, plaintext_token=plaintext)

    async def list_tokens(self, organization_id: str) -> list[ScimToken]:
        return await self.tokens.list_for_organization(organization_id)

    async def revoke_token(
        self, *, organization_id: str, token_id: str, actor_user_id: str
    ) -> bool:
        revoked = await self.tokens.revoke(
            organization_id=organization_id, token_id=token_id
        )
        if revoked:
            await self.audit.record(
                action="scim_token.revoked",
                outcome="success",
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                target=token_id,
            )
        return revoked

    async def authenticate(self, plaintext_token: str) -> ScimToken | None:
        """Resolves a presented SCIM bearer token to its row.

        `None` for anything unusable — wrong prefix, unknown hash,
        revoked — without distinguishing them (CLAUDE.md §10: uniform,
        information-minimal auth failures).
        """
        if not plaintext_token.startswith(_TOKEN_PREFIX):
            return None
        token = await self.tokens.find_active_by_hash(_hash_token(plaintext_token))
        if token is None:
            return None
        await self.tokens.touch_last_used(token.id)
        return token

    # --- provisioning (IdP-facing) --------------------------------------

    async def list_users(
        self, *, organization_id: str, email: str | None, start_index: int, count: int
    ) -> tuple[list[ScimUser], int]:
        return await self.directory.list_users(
            organization_id=organization_id,
            email=email,
            start_index=start_index,
            count=count,
        )

    async def get_user(self, *, organization_id: str, user_id: str) -> ScimUser | None:
        return await self.directory.get_user(
            organization_id=organization_id, user_id=user_id
        )

    async def provision_user(
        self, *, organization_id: str, email: str, display_name: str
    ) -> ScimUser:
        user = await self.directory.create_user(
            organization_id=organization_id,
            email=email,
            display_name=display_name,
            role=DEFAULT_PROVISIONED_ROLE,
        )
        await self.audit.record(
            action="scim.user_provisioned",
            outcome="success",
            organization_id=organization_id,
            actor_user_id=None,  # the actor is an IdP, not a person
            target=user.user_id,
            metadata={"email": email},
        )
        return user

    async def set_user_active(
        self, *, organization_id: str, user_id: str, active: bool
    ) -> ScimUser | None:
        user = await self.directory.set_active(
            organization_id=organization_id, user_id=user_id, active=active
        )
        if user is not None:
            await self.audit.record(
                action="scim.user_activated" if active else "scim.user_deactivated",
                outcome="success",
                organization_id=organization_id,
                actor_user_id=None,
                target=user_id,
            )
        return user

    async def set_user_display_name(
        self, *, organization_id: str, user_id: str, display_name: str
    ) -> ScimUser | None:
        return await self.directory.set_display_name(
            organization_id=organization_id, user_id=user_id, display_name=display_name
        )

    async def deprovision_user(self, *, organization_id: str, user_id: str) -> bool:
        removed = await self.directory.remove_user(
            organization_id=organization_id, user_id=user_id
        )
        if removed:
            await self.audit.record(
                action="scim.user_deprovisioned",
                outcome="success",
                organization_id=organization_id,
                actor_user_id=None,
                target=user_id,
            )
        return removed

    async def list_groups(self, organization_id: str) -> list[Workspace]:
        return await self.directory.list_groups(organization_id)

    async def get_group(
        self, *, organization_id: str, workspace_id: str
    ) -> Workspace | None:
        return await self.directory.get_group(
            organization_id=organization_id, workspace_id=workspace_id
        )
