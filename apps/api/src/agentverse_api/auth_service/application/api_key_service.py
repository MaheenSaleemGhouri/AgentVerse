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
from agentverse_api.auth_service.domain.entities import ApiKey
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
        self, *, workspace_id: str, name: str, created_by_user_id: str
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

    async def revoke_api_key(self, *, api_key_id: str, actor_user_id: str) -> None:
        key = await self.api_keys.get_api_key(api_key_id)
        await self.api_keys.revoke_api_key(api_key_id)
        await self.audit.record(
            action="api_key.revoked",
            outcome="success",
            workspace_id=key.workspace_id if key is not None else None,
            actor_user_id=actor_user_id,
            target=api_key_id,
        )
