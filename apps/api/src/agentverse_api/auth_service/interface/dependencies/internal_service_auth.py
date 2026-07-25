"""Shared-secret check for server-to-server calls (e.g. apps/web's Better
Auth hooks). Zero trust: the internal network boundary alone is not
sufficient authorization (CLAUDE.md §10) — every internal call still
carries a verifiable credential.
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from agentverse_api.infrastructure.config import get_settings

_HEADER_NAME = "X-Internal-Secret"


async def require_internal_service(
    x_internal_secret: str | None = Header(default=None, alias=_HEADER_NAME),
) -> None:
    settings = get_settings()
    if x_internal_secret is None or not hmac.compare_digest(
        x_internal_secret, settings.internal_api_secret
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
