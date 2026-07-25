"""Verifies Better Auth-issued JWTs against its JWKS endpoint (ADR-0005).

This module is intentionally synchronous — `PyJWKClient` performs
blocking network I/O (and in-memory-cached lookups thereafter). Callers
in the async interface layer offload it via `run_in_threadpool`
(CLAUDE.md §7: no blocking call inside `async def`); this module itself
never imports FastAPI/Starlette.
"""

from __future__ import annotations

from functools import lru_cache

import jwt
from jwt import PyJWKClient

ALGORITHM = "EdDSA"


class InvalidIdentityTokenError(Exception):
    """Token failed signature, claim, or shape validation."""


class JwtVerifier:
    def __init__(self, *, jwks_url: str, issuer: str, audience: str) -> None:
        self._jwks_client = PyJWKClient(jwks_url)
        self._issuer = issuer
        self._audience = audience

    def verify_and_get_user_id(self, token: str) -> str:
        """Returns the verified token's `sub` claim (Better Auth's user id)."""
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=[ALGORITHM],
                audience=self._audience,
                issuer=self._issuer,
            )
        except jwt.PyJWTError as exc:
            raise InvalidIdentityTokenError(str(exc)) from exc

        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise InvalidIdentityTokenError("token has no subject claim")
        return subject


@lru_cache
def get_jwt_verifier(*, jwks_url: str, issuer: str, audience: str) -> JwtVerifier:
    """Process-wide singleton per (jwks_url, issuer, audience) — reuses
    `PyJWKClient`'s internal key cache across requests instead of
    re-fetching the JWKS document every time.
    """
    return JwtVerifier(jwks_url=jwks_url, issuer=issuer, audience=audience)
