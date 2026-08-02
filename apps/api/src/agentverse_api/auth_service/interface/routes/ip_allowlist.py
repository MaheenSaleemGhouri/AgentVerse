"""`/api/v1/workspaces/{workspace_id}/ip-allowlist` — manage the opt-in
IP restriction (Increment 7.4). Admin-gated: changing who can reach a
workspace is a sensitive access-control action.

Deliberately **not** protected by `enforce_ip_allowlist` itself — an
admin who mistypes a CIDR and locks themselves out must still be able to
reach this endpoint to fix it. Locking the escape hatch behind the lock
is how an allowlist becomes an outage.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from agentverse_api.auth_service.application.ip_allowlist_service import IpAllowlistService
from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.domain.exceptions import InvalidCidrError
from agentverse_api.auth_service.interface.dependencies.require_role import require_admin
from agentverse_api.auth_service.interface.dependencies.services import get_ip_allowlist_service
from agentverse_api.auth_service.interface.schemas.ip_allowlist import (
    AddIpAllowlistEntryRequest,
    IpAllowlistEntryResponse,
)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/ip-allowlist", tags=["ip-allowlist"]
)


@router.get("", response_model=list[IpAllowlistEntryResponse])
async def list_ip_allowlist(
    context: WorkspaceContext = Depends(require_admin),
    service: IpAllowlistService = Depends(get_ip_allowlist_service),
) -> list[IpAllowlistEntryResponse]:
    entries = await service.list_entries(context.workspace_id)
    return [
        IpAllowlistEntryResponse.model_validate(entry, from_attributes=True)
        for entry in entries
    ]


@router.post("", response_model=IpAllowlistEntryResponse, status_code=status.HTTP_201_CREATED)
async def add_ip_allowlist_entry(
    body: AddIpAllowlistEntryRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: IpAllowlistService = Depends(get_ip_allowlist_service),
) -> IpAllowlistEntryResponse:
    try:
        entry = await service.add_entry(
            workspace_id=context.workspace_id,
            cidr=body.cidr,
            label=body.label,
            actor_user_id=context.user_id,
        )
    except InvalidCidrError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return IpAllowlistEntryResponse.model_validate(entry, from_attributes=True)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def remove_ip_allowlist_entry(
    entry_id: str,
    context: WorkspaceContext = Depends(require_admin),
    service: IpAllowlistService = Depends(get_ip_allowlist_service),
) -> None:
    await service.remove_entry(
        workspace_id=context.workspace_id,
        entry_id=entry_id,
        actor_user_id=context.user_id,
    )
