"""SCIM 2.0 provisioning endpoints (RFC 7644).

Mounted at `/scim/v2`, deliberately *outside* `/api/v1`: SCIM's paths,
media type (`application/scim+json`), error envelope and pagination are
all fixed by the RFC, and identity providers validate them strictly.
Forcing them into AgentVerse's own `/api/v1` conventions — the standard
`{"error": {...}}` envelope, cursor pagination — would produce something
no IdP could talk to. `api-designer`'s envelope owns AgentVerse's API;
this surface answers to the RFC, and that exemption is the whole reason
it lives at its own prefix rather than quietly deviating inside `/v1`.

The organization is resolved from the bearer token, never the path
(`dependencies/scim_auth.py`).

**Groups are read-only.** They expose the organization's workspaces as a
directory so an IdP can display them; they cannot be written, because
organization membership grants no workspace access (ADR-0011) and a
writable Groups endpoint would invert that from an IdP config page.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse

from agentverse_api.auth_service.application.scim_service import ScimService
from agentverse_api.auth_service.domain.entities import ScimUser, Workspace
from agentverse_api.auth_service.interface.dependencies.scim_auth import get_scim_organization
from agentverse_api.auth_service.interface.dependencies.services import get_scim_service
from agentverse_api.auth_service.interface.schemas.scim import (
    GROUP_SCHEMA,
    USER_SCHEMA,
    ScimCreateUserRequest,
    ScimEmail,
    ScimError,
    ScimFilterUnsupportedError,
    ScimGroupResource,
    ScimListResponse,
    ScimMeta,
    ScimName,
    ScimPatchRequest,
    ScimUserResource,
    parse_username_filter,
)

#: RFC 7644 §3.1 — SCIM has its own media type. IdPs check it.
SCIM_MEDIA_TYPE = "application/scim+json"

router = APIRouter(prefix="/scim/v2", tags=["scim"])


def _scim_error(*, status_code: int, detail: str, scim_type: str | None = None) -> JSONResponse:
    body = ScimError(status=str(status_code), detail=detail, scimType=scim_type)
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),
        media_type=SCIM_MEDIA_TYPE,
    )


def _user_resource(user: ScimUser) -> ScimUserResource:
    return ScimUserResource(
        id=user.user_id,
        userName=user.email,
        displayName=user.display_name,
        name=ScimName(formatted=user.display_name),
        emails=[ScimEmail(value=user.email, primary=True, type="work")],
        active=user.active,
        meta=ScimMeta(
            resourceType="User",
            created=user.created_at.isoformat(),
            lastModified=user.created_at.isoformat(),
        ),
    )


def _group_resource(workspace: Workspace) -> ScimGroupResource:
    return ScimGroupResource(
        id=workspace.id,
        displayName=workspace.name,
        meta=ScimMeta(
            resourceType="Group",
            created=workspace.created_at.isoformat(),
            lastModified=workspace.created_at.isoformat(),
        ),
    )


def _scim_json(payload: object, *, status_code: int = status.HTTP_200_OK) -> JSONResponse:
    dumped = payload.model_dump() if hasattr(payload, "model_dump") else payload
    return JSONResponse(status_code=status_code, content=dumped, media_type=SCIM_MEDIA_TYPE)


@router.get("/ServiceProviderConfig")
async def service_provider_config(request: Request) -> JSONResponse:
    """Advertises exactly what this implementation supports.

    Honest by construction: `patch` true, `filter` true (with a low
    `maxResults` reflecting the single supported filter form), and
    `bulk`/`sort`/`etag`/`changePassword` all false, because none of
    them are implemented. An IdP reads this to decide what to send.
    """
    return _scim_json(
        {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
            "documentationUri": f"{request.base_url}docs",
            "patch": {"supported": True},
            "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
            "filter": {"supported": True, "maxResults": 200},
            "changePassword": {"supported": False},
            "sort": {"supported": False},
            "etag": {"supported": False},
            "authenticationSchemes": [
                {
                    "type": "oauthbearertoken",
                    "name": "OAuth Bearer Token",
                    "description": "An AgentVerse SCIM token, issued per organization.",
                    "primary": True,
                }
            ],
        }
    )


@router.get("/Users")
async def list_users(
    filter: str | None = Query(default=None),  # noqa: A002 - the RFC names it `filter`
    startIndex: int = Query(default=1, ge=1),  # noqa: N803 - SCIM wire name
    count: int = Query(default=100, ge=1, le=200),
    organization_id: str = Depends(get_scim_organization),
    service: ScimService = Depends(get_scim_service),
) -> JSONResponse:
    try:
        email = parse_username_filter(filter)
    except ScimFilterUnsupportedError as exc:
        return _scim_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            scim_type="invalidFilter",
        )

    users, total = await service.list_users(
        organization_id=organization_id, email=email, start_index=startIndex, count=count
    )
    body = ScimListResponse(
        totalResults=total,
        startIndex=startIndex,
        itemsPerPage=len(users),
        Resources=[_user_resource(user).model_dump() for user in users],
    )
    return _scim_json(body)


@router.get("/Users/{user_id}")
async def get_user(
    user_id: str,
    organization_id: str = Depends(get_scim_organization),
    service: ScimService = Depends(get_scim_service),
) -> JSONResponse:
    user = await service.get_user(organization_id=organization_id, user_id=user_id)
    if user is None:
        # 404 for "not in this organization" as much as "does not
        # exist" — a token holder must not be able to probe for accounts
        # outside its own tenant (Rule 11).
        return _scim_error(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _scim_json(_user_resource(user))


@router.post("/Users", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: ScimCreateUserRequest,
    organization_id: str = Depends(get_scim_organization),
    service: ScimService = Depends(get_scim_service),
) -> JSONResponse:
    user = await service.provision_user(
        organization_id=organization_id,
        email=body.resolved_email(),
        display_name=body.resolved_display_name(),
    )
    if not body.active:
        deactivated = await service.set_user_active(
            organization_id=organization_id, user_id=user.user_id, active=False
        )
        user = deactivated or user
    return _scim_json(_user_resource(user), status_code=status.HTTP_201_CREATED)


@router.patch("/Users/{user_id}")
async def patch_user(
    user_id: str,
    body: ScimPatchRequest,
    organization_id: str = Depends(get_scim_organization),
    service: ScimService = Depends(get_scim_service),
) -> JSONResponse:
    current = await service.get_user(organization_id=organization_id, user_id=user_id)
    if current is None:
        return _scim_error(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    display_name = body.resolved_display_name()
    if display_name is not None:
        current = (
            await service.set_user_display_name(
                organization_id=organization_id,
                user_id=user_id,
                display_name=display_name,
            )
            or current
        )

    active = body.resolved_active()
    if active is not None:
        current = (
            await service.set_user_active(
                organization_id=organization_id, user_id=user_id, active=active
            )
            or current
        )

    return _scim_json(_user_resource(current))


@router.put("/Users/{user_id}")
async def replace_user(
    user_id: str,
    body: ScimCreateUserRequest,
    organization_id: str = Depends(get_scim_organization),
    service: ScimService = Depends(get_scim_service),
) -> JSONResponse:
    """PUT replaces the mutable attributes this service stores. It never
    re-keys the account: `userName` is the identity SSO asserts, and
    silently rewriting it would orphan the person from their sign-in.
    """
    current = await service.get_user(organization_id=organization_id, user_id=user_id)
    if current is None:
        return _scim_error(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    updated = await service.set_user_display_name(
        organization_id=organization_id,
        user_id=user_id,
        display_name=body.resolved_display_name(),
    )
    updated = (
        await service.set_user_active(
            organization_id=organization_id, user_id=user_id, active=body.active
        )
        or updated
        or current
    )
    return _scim_json(_user_resource(updated))


@router.delete("/Users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    organization_id: str = Depends(get_scim_organization),
    service: ScimService = Depends(get_scim_service),
) -> Response:
    removed = await service.deprovision_user(organization_id=organization_id, user_id=user_id)
    if not removed:
        return _scim_error(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/Groups")
async def list_groups(
    startIndex: int = Query(default=1, ge=1),  # noqa: N803 - SCIM wire name
    count: int = Query(default=100, ge=1, le=200),
    organization_id: str = Depends(get_scim_organization),
    service: ScimService = Depends(get_scim_service),
) -> JSONResponse:
    workspaces = await service.list_groups(organization_id)
    page = workspaces[startIndex - 1 : startIndex - 1 + count]
    body = ScimListResponse(
        totalResults=len(workspaces),
        startIndex=startIndex,
        itemsPerPage=len(page),
        Resources=[_group_resource(workspace).model_dump() for workspace in page],
    )
    return _scim_json(body)


@router.get("/Groups/{group_id}")
async def get_group(
    group_id: str,
    organization_id: str = Depends(get_scim_organization),
    service: ScimService = Depends(get_scim_service),
) -> JSONResponse:
    workspace = await service.get_group(organization_id=organization_id, workspace_id=group_id)
    if workspace is None:
        return _scim_error(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return _scim_json(_group_resource(workspace))


@router.post("/Groups", status_code=status.HTTP_501_NOT_IMPLEMENTED)
@router.patch("/Groups/{group_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
@router.put("/Groups/{group_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
@router.delete("/Groups/{group_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def groups_are_read_only(
    organization_id: str = Depends(get_scim_organization),
) -> JSONResponse:
    """Answers group writes with an explicit 501 rather than a 404 or a
    silent success — an IdP administrator needs to know push-groups is
    unsupported, not be left believing it worked.
    """
    return _scim_error(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Groups are read-only. Organization membership does not grant workspace "
            "access in AgentVerse, so workspace membership cannot be provisioned over SCIM."
        ),
    )


__all__ = ["router", "SCIM_MEDIA_TYPE", "USER_SCHEMA", "GROUP_SCHEMA"]
