"""Resolves the organization a SCIM request acts on, from its bearer
token alone.

The organization is never taken from the URL or the payload: an IdP is
configured with one base URL and one token, and letting the path select
the tenant would make a leaked token usable against every organization.
This mirrors how `get_current_workspace` refuses to trust a path
`workspace_id` (ADR-0004) — the credential decides the tenant.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agentverse_api.auth_service.application.scim_service import ScimService
from agentverse_api.auth_service.interface.dependencies.services import get_scim_service

_scim_bearer = HTTPBearer(auto_error=False)


async def get_scim_organization(
    credentials: HTTPAuthorizationCredentials | None = Depends(_scim_bearer),
    service: ScimService = Depends(get_scim_service),
) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing SCIM bearer token"
        )

    token = await service.authenticate(credentials.credentials)
    if token is None:
        # One message for missing, malformed, unknown and revoked — a
        # caller probing tokens learns nothing from the difference.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked SCIM token"
        )

    return token.organization_id
