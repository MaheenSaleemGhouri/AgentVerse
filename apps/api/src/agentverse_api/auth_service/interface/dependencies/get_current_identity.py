"""Verifies the request's Better Auth JWT and resolves the caller's user id.

This is the *only* place `user_id` is trusted from (ADR-0004) — every
other dependency in this service takes it from here, never from a body
or query parameter.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from agentverse_api.auth_service.infrastructure.jwt_verifier import (
    InvalidIdentityTokenError,
    get_jwt_verifier,
)
from agentverse_api.infrastructure.config import get_settings

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    settings = get_settings()
    verifier = get_jwt_verifier(
        jwks_url=settings.auth_jwks_url,
        issuer=settings.auth_public_url,
        audience=settings.auth_public_url,
    )
    try:
        # PyJWKClient performs blocking network I/O — offloaded per
        # CLAUDE.md §7 (no blocking call inside `async def`).
        user_id = await run_in_threadpool(verifier.verify_and_get_user_id, credentials.credentials)
    except InvalidIdentityTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc

    return user_id
