"""Security Center endpoints.

Split by what the data is *about*, which is also what decides who may
read it:

* `/api/v1/me/security/...` — events and devices belonging to the
  calling identity. No workspace involved; a user always sees their own
  security history, and never anyone else's.
* `/api/v1/workspaces/{id}/security/...` — the workspace-wide feed and
  score, admin-gated.
* `/api/v1/organizations/{id}/password-policy` — org-scoped policy,
  readable by any member (people need to know the rules they must
  satisfy), writable by admins.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from agentverse_api.auth_service.application.security_service import SecurityService
from agentverse_api.auth_service.domain.entities import (
    OrganizationContext,
    SecurityEvent,
    TrustedDevice,
    WorkspaceContext,
)
from agentverse_api.auth_service.domain.security import PasswordPolicy, SecuritySeverity
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
)
from agentverse_api.auth_service.interface.dependencies.require_org_role import (
    require_org_admin,
    require_org_viewer,
)
from agentverse_api.auth_service.interface.dependencies.require_role import require_admin
from agentverse_api.auth_service.interface.dependencies.services import (
    get_security_posture_reader,
    get_security_service,
)
from agentverse_api.auth_service.interface.schemas.security import (
    CheckPasswordRequest,
    CheckPasswordResponse,
    PasswordPolicyResponse,
    ScoreFactorResponse,
    SecurityEventResponse,
    SecurityScoreResponse,
    TrustDeviceRequest,
    TrustedDeviceResponse,
    UpdatePasswordPolicyRequest,
)
from agentverse_api.auth_service.interface.security_posture import SecurityPostureReader

router = APIRouter(tags=["security"])


def _event_response(event: SecurityEvent) -> SecurityEventResponse:
    return SecurityEventResponse(
        id=event.id,
        user_id=event.user_id,
        workspace_id=event.workspace_id,
        organization_id=event.organization_id,
        event_type=event.event_type,
        severity=event.severity,
        ip_address=event.ip_address,
        user_agent=event.user_agent,
        metadata=event.metadata,
        created_at=event.created_at,
    )


def _device_response(device: TrustedDevice) -> TrustedDeviceResponse:
    return TrustedDeviceResponse(
        id=device.id,
        device_fingerprint=device.device_fingerprint,
        device_name=device.device_name,
        user_agent=device.user_agent,
        ip_address=device.ip_address,
        trusted_at=device.trusted_at,
        last_seen_at=device.last_seen_at,
        revoked_at=device.revoked_at,
    )


# -- the calling identity's own security history -------------------------


@router.get("/api/v1/me/security/events", response_model=list[SecurityEventResponse])
async def list_my_security_events(
    limit: int = Query(default=50, ge=1, le=200),
    severity: SecuritySeverity | None = Query(default=None),
    user_id: str = Depends(get_current_identity),
    service: SecurityService = Depends(get_security_service),
) -> list[SecurityEventResponse]:
    events = await service.list_user_events(user_id, limit=limit, severity=severity)
    return [_event_response(event) for event in events]


@router.get("/api/v1/me/security/devices", response_model=list[TrustedDeviceResponse])
async def list_my_devices(
    user_id: str = Depends(get_current_identity),
    service: SecurityService = Depends(get_security_service),
) -> list[TrustedDeviceResponse]:
    devices = await service.list_devices(user_id)
    return [_device_response(device) for device in devices]


@router.post(
    "/api/v1/me/security/devices",
    response_model=TrustedDeviceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def trust_my_device(
    body: TrustDeviceRequest,
    user_id: str = Depends(get_current_identity),
    service: SecurityService = Depends(get_security_service),
) -> TrustedDeviceResponse:
    device = await service.trust_device(
        user_id=user_id,
        device_fingerprint=body.device_fingerprint,
        device_name=body.device_name,
        user_agent=None,
        ip_address=None,
    )
    return _device_response(device)


@router.delete(
    "/api/v1/me/security/devices/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def revoke_my_device(
    device_id: str,
    user_id: str = Depends(get_current_identity),
    service: SecurityService = Depends(get_security_service),
) -> None:
    device = await service.revoke_device(user_id=user_id, device_id=device_id)
    if device is None:
        # Another user's device id reads exactly like a nonexistent one
        # — the revoke is scoped by user_id in SQL, so this is a 404 by
        # construction rather than by a separate ownership check.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")


# -- workspace-wide -------------------------------------------------------


@router.get(
    "/api/v1/workspaces/{workspace_id}/security/events",
    response_model=list[SecurityEventResponse],
)
async def list_workspace_security_events(
    limit: int = Query(default=50, ge=1, le=200),
    severity: SecuritySeverity | None = Query(default=None),
    context: WorkspaceContext = Depends(require_admin),
    service: SecurityService = Depends(get_security_service),
) -> list[SecurityEventResponse]:
    events = await service.list_workspace_events(
        context.workspace_id, limit=limit, severity=severity
    )
    return [_event_response(event) for event in events]


@router.get(
    "/api/v1/workspaces/{workspace_id}/security/score",
    response_model=SecurityScoreResponse,
)
async def get_security_score(
    context: WorkspaceContext = Depends(require_admin),
    service: SecurityService = Depends(get_security_service),
    posture: SecurityPostureReader = Depends(get_security_posture_reader),
) -> SecurityScoreResponse:
    facts = await posture.gather(context.workspace_id)
    score = await service.security_score(
        workspace_id=context.workspace_id,
        two_factor_enabled_members=facts.two_factor_enabled_members,
        total_members=facts.total_members,
        ip_allowlist_configured=facts.ip_allowlist_configured,
        sso_enforced=facts.sso_enforced,
        password_policy_configured=facts.password_policy_configured,
        non_expiring_api_keys=facts.non_expiring_api_keys,
    )
    return SecurityScoreResponse(
        score=score.score,
        grade=score.grade,
        factors=[
            ScoreFactorResponse(
                key=factor.key,
                label=factor.label,
                earned=factor.earned,
                possible=factor.possible,
                remediation=factor.remediation,
            )
            for factor in score.factors
        ],
    )


# -- organization password policy ----------------------------------------


@router.get(
    "/api/v1/organizations/{organization_id}/password-policy",
    response_model=PasswordPolicyResponse,
)
async def get_password_policy(
    context: OrganizationContext = Depends(require_org_viewer),
    service: SecurityService = Depends(get_security_service),
) -> PasswordPolicyResponse:
    policy, configured = await service.get_policy(context.organization_id)
    return PasswordPolicyResponse(
        min_length=policy.min_length,
        require_uppercase=policy.require_uppercase,
        require_lowercase=policy.require_lowercase,
        require_number=policy.require_number,
        require_symbol=policy.require_symbol,
        max_age_days=policy.max_age_days,
        is_configured=configured,
    )


@router.put(
    "/api/v1/organizations/{organization_id}/password-policy",
    response_model=PasswordPolicyResponse,
)
async def set_password_policy(
    body: UpdatePasswordPolicyRequest,
    context: OrganizationContext = Depends(require_org_admin),
    service: SecurityService = Depends(get_security_service),
) -> PasswordPolicyResponse:
    saved = await service.set_policy(
        organization_id=context.organization_id,
        actor_user_id=context.user_id,
        policy=PasswordPolicy(
            min_length=body.min_length,
            require_uppercase=body.require_uppercase,
            require_lowercase=body.require_lowercase,
            require_number=body.require_number,
            require_symbol=body.require_symbol,
            max_age_days=body.max_age_days,
        ),
    )
    return PasswordPolicyResponse(
        min_length=saved.min_length,
        require_uppercase=saved.require_uppercase,
        require_lowercase=saved.require_lowercase,
        require_number=saved.require_number,
        require_symbol=saved.require_symbol,
        max_age_days=saved.max_age_days,
        is_configured=True,
    )


@router.post(
    "/api/v1/organizations/{organization_id}/password-policy/check",
    response_model=CheckPasswordResponse,
)
async def check_password(
    body: CheckPasswordRequest,
    context: OrganizationContext = Depends(require_org_viewer),
    service: SecurityService = Depends(get_security_service),
) -> CheckPasswordResponse:
    """Validates a candidate password against the organization's policy.

    The password is never stored or logged — it is checked and
    discarded. This exists so the sign-up/change-password UI can show
    the real rules rather than a client-side guess at them, while the
    same policy is still enforced server-side on the actual change.
    """
    violations = await service.check_password(
        organization_id=context.organization_id, password=body.password
    )
    return CheckPasswordResponse(violations=violations)
