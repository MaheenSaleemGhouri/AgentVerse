"""Verifies the request's Better Auth JWT and resolves the caller's user id.

This is the *only* place a `user_id` is trusted from a user session
(ADR-0004) — every other dependency in this service takes it from here,
never from a body or query parameter.

Programmatic callers present an API key instead of a JWT; that path is
`get_current_workspace`'s, and it reuses `verify_identity_token` here for
the session case rather than duplicating verification.
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

bearer_scheme = HTTPBearer(auto_error=False)

#: Every AgentVerse API key carries this prefix (`api_key_service`), so a
#: presented credential can be routed to the right verifier without
#: attempting — and failing — JWT verification first.
API_KEY_PREFIX = "av_live_"


async def verify_identity_token(token: str) -> str:
    """Verifies a Better Auth JWT and returns its subject."""
    settings = get_settings()
    verifier = get_jwt_verifier(
        jwks_url=settings.auth_jwks_url,
        issuer=settings.auth_public_url,
        audience=settings.auth_public_url,
    )
    try:
        # PyJWKClient performs blocking network I/O — offloaded per
        # CLAUDE.md §7 (no blocking call inside `async def`).
        user_id = await run_in_threadpool(verifier.verify_and_get_user_id, token)
    except InvalidIdentityTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc
    return user_id


async def get_current_identity_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str | None:
    """The session user id, or `None` when the caller presented an API key.

    `get_current_workspace` depends on this rather than on
    `get_current_identity` so that an API key reaches its own resolution
    path instead of being rejected as a malformed JWT.
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    if credentials.credentials.startswith(API_KEY_PREFIX):
        return None

    return await verify_identity_token(credentials.credentials)


async def get_current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    if credentials.credentials.startswith(API_KEY_PREFIX):
        # Routes depending on this dependency are user-session surfaces
        # (workspace/organization management, invitation acceptance).
        # An API key is a workspace-scoped credential with no user
        # session behind it, so it is rejected here rather than silently
        # resolved to its issuer — which would let a key act on the
        # issuer's *other* workspaces.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This endpoint requires a user session, not an API key",
        )

    return await verify_identity_token(credentials.credentials)
