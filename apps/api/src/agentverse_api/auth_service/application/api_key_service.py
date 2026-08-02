"""API key issuance/rotation (docs/roadmap.md Phase 1 technical tasks).

Keys are workspace-scoped, hashed at rest with a fast hash — they are
already high-entropy secrets, unlike user passwords, so Argon2id/bcrypt
would be pure overhead here (CLAUDE.md §10's own distinction). Shown in
full exactly once, at issuance.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.api_key_scope import ApiKeyScope
from agentverse_api.auth_service.domain.entities import ApiKey
from agentverse_api.auth_service.domain.exceptions import ApiKeyNotFoundError
from agentverse_api.auth_service.domain.ports import ApiKeyRepository

_KEY_PREFIX = "av_live_"
_SECRET_BYTES = 32


def _hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class IssuedApiKey:
    entity: ApiKey
    plaintext_key: str


@dataclass(slots=True)
class ApiKeyService:
    api_keys: ApiKeyRepository
    audit: AuditService

    async def issue_api_key(
        self,
        *,
        workspace_id: str,
        name: str,
        created_by_user_id: str,
        scope: ApiKeyScope = ApiKeyScope.FULL,
        tier: str = "standard",
    ) -> IssuedApiKey:
        secret = secrets.token_urlsafe(_SECRET_BYTES)
        plaintext_key = f"{_KEY_PREFIX}{secret}"
        display_prefix = plaintext_key[: len(_KEY_PREFIX) + 6]

        entity = await self.api_keys.create_api_key(
            workspace_id=workspace_id,
            name=name,
            key_prefix=display_prefix,
            hashed_key=_hash_key(plaintext_key),
            created_by_user_id=created_by_user_id,
            scope=scope,
            tier=tier,
        )
        await self.audit.record(
            action="api_key.issued",
            outcome="success",
            workspace_id=workspace_id,
            actor_user_id=created_by_user_id,
            target=entity.id,
            metadata={"name": name},
        )
        return IssuedApiKey(entity=entity, plaintext_key=plaintext_key)

    async def list_api_keys(self, workspace_id: str) -> list[ApiKey]:
        return await self.api_keys.list_api_keys(workspace_id)

    async def authenticate(self, plaintext_key: str) -> ApiKey | None:
        """Resolves a presented bearer credential to its key row.

        Returns `None` for anything unusable — wrong prefix, unknown
        hash, revoked key — deliberately without distinguishing them, so
        a caller probing keys learns nothing from the difference
        (CLAUDE.md §10: uniform, information-minimal auth failures).
        """
        if not plaintext_key.startswith(_KEY_PREFIX):
            return None
        key = await self.api_keys.find_active_by_hash(_hash_key(plaintext_key))
        if key is None:
            return None
        await self.api_keys.touch_last_used(key.id)
        return key

    async def revoke_api_key(
        self, *, workspace_id: str, api_key_id: str, actor_user_id: str
    ) -> None:
        key = await self.api_keys.get_api_key(api_key_id)
        if key is None or key.workspace_id != workspace_id:
            # Same guard `rotate_api_key` already applied: without it, an
            # admin of one workspace could revoke another tenant's key by
            # id alone (Rule 11). Indistinguishable from "no such key".
            raise ApiKeyNotFoundError(api_key_id)

        await self.api_keys.revoke_api_key(api_key_id)
        await self.audit.record(
            action="api_key.revoked",
            outcome="success",
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            target=api_key_id,
        )

    async def rotate_api_key(
        self, *, workspace_id: str, api_key_id: str, actor_user_id: str
    ) -> IssuedApiKey:
        """Revokes the old key and issues its replacement in one logical
        step: same workspace/name/scope/tier, linked via
        `rotated_from_id` so the audit trail reads as a rotation, not an
        unrelated revoke plus an unrelated issue.
        """
        old = await self.api_keys.get_api_key(api_key_id)
        if old is None or old.workspace_id != workspace_id:
            # Identical error for "doesn't exist" and "exists in another
            # workspace" — a guessed cross-workspace id must not be
            # distinguishable from one that simply isn't real (Rule 11).
            raise ApiKeyNotFoundError(api_key_id)

        await self.api_keys.revoke_api_key(api_key_id)

        secret = secrets.token_urlsafe(_SECRET_BYTES)
        plaintext_key = f"{_KEY_PREFIX}{secret}"
        display_prefix = plaintext_key[: len(_KEY_PREFIX) + 6]
        new_entity = await self.api_keys.create_api_key(
            workspace_id=workspace_id,
            name=old.name,
            key_prefix=display_prefix,
            hashed_key=_hash_key(plaintext_key),
            created_by_user_id=actor_user_id,
            scope=old.scope,
            tier=old.tier,
            rotated_from_id=old.id,
        )
        await self.audit.record(
            action="api_key.rotated",
            outcome="success",
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            target=new_entity.id,
            metadata={"rotated_from_id": old.id},
        )
        return IssuedApiKey(entity=new_entity, plaintext_key=plaintext_key)
