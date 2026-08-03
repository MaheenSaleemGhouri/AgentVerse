"""Security Center use cases: the security-event feed, trusted-device
management, password policy, and the security score.

Suspicious-activity detection lives here rather than in the repository
because it is a *decision* about what a pattern of events means, not a
storage concern — and keeping it here means it can be tested against a
fake repository without a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.entities import SecurityEvent, TrustedDevice
from agentverse_api.auth_service.domain.ports import (
    PasswordPolicyRepository,
    SecurityEventRepository,
    TrustedDeviceRepository,
)
from agentverse_api.auth_service.domain.security import (
    DEFAULT_PASSWORD_POLICY,
    PasswordPolicy,
    SecurityEventType,
    SecurityPosture,
    SecurityScore,
    SecuritySeverity,
    compute_security_score,
    password_violations,
)

#: A burst of failures inside this window is treated as an attack
#: pattern rather than a forgetful user. Deliberately short: spread the
#: window wide enough and ordinary "wrong password three times over a
#: week" starts alerting, which trains people to ignore the alert.
_RAPID_FAILURE_WINDOW = timedelta(minutes=15)
_RAPID_FAILURE_THRESHOLD = 5

#: The score's incident window. Matches the 30-day framing the UI uses,
#: defined once here so the two cannot drift.
_INCIDENT_WINDOW = timedelta(days=30)


@dataclass(slots=True)
class SecurityService:
    events: SecurityEventRepository
    devices: TrustedDeviceRepository
    policies: PasswordPolicyRepository
    audit: AuditService

    # -- events ------------------------------------------------------

    async def record_event(
        self,
        *,
        event_type: SecurityEventType,
        user_id: str | None = None,
        workspace_id: str | None = None,
        organization_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> SecurityEvent:
        return await self.events.record(
            user_id=user_id,
            workspace_id=workspace_id,
            organization_id=organization_id,
            event_type=event_type,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=metadata or {},
        )

    async def record_login_attempt(
        self,
        *,
        user_id: str,
        succeeded: bool,
        device_fingerprint: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> list[SecurityEvent]:
        """Record a sign-in and any signal it implies.

        Returns every event written, so a caller (and a test) can see
        that one login produced both the failure and the escalation,
        rather than having to infer it.
        """
        written: list[SecurityEvent] = []

        if not succeeded:
            written.append(
                await self.record_event(
                    event_type=SecurityEventType.LOGIN_FAILED,
                    user_id=user_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            )
            # Escalate only once the burst threshold is crossed. The
            # count includes the failure just written, which is why the
            # comparison is `>=` and not `>`.
            recent = await self.events.count_recent_failures(
                user_id=user_id, since=datetime.now(UTC) - _RAPID_FAILURE_WINDOW
            )
            if recent >= _RAPID_FAILURE_THRESHOLD:
                written.append(
                    await self.record_event(
                        event_type=SecurityEventType.SUSPICIOUS_RAPID_FAILURES,
                        user_id=user_id,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        metadata={"failures": str(recent)},
                    )
                )
            return written

        # A successful login from a device the user has never confirmed
        # is the alert worth sending — an unrecognised *and* successful
        # sign-in is what account takeover looks like.
        if device_fingerprint is not None:
            known = await self.devices.get(user_id=user_id, device_fingerprint=device_fingerprint)
            if known is None or not known.is_active:
                written.append(
                    await self.record_event(
                        event_type=SecurityEventType.LOGIN_NEW_DEVICE,
                        user_id=user_id,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                )
            else:
                await self.devices.upsert(
                    user_id=user_id,
                    device_fingerprint=device_fingerprint,
                    device_name=known.device_name,
                    user_agent=user_agent,
                    ip_address=ip_address,
                )
        return written

    async def list_user_events(
        self, user_id: str, *, limit: int = 50, severity: SecuritySeverity | None = None
    ) -> list[SecurityEvent]:
        return await self.events.list_for_user(user_id, limit=limit, severity=severity)

    async def list_workspace_events(
        self, workspace_id: str, *, limit: int = 50, severity: SecuritySeverity | None = None
    ) -> list[SecurityEvent]:
        return await self.events.list_for_workspace(workspace_id, limit=limit, severity=severity)

    # -- trusted devices ---------------------------------------------

    async def list_devices(self, user_id: str) -> list[TrustedDevice]:
        return await self.devices.list_for_user(user_id)

    async def trust_device(
        self,
        *,
        user_id: str,
        device_fingerprint: str,
        device_name: str | None,
        user_agent: str | None,
        ip_address: str | None,
    ) -> TrustedDevice:
        device = await self.devices.upsert(
            user_id=user_id,
            device_fingerprint=device_fingerprint,
            device_name=device_name,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        await self.record_event(
            event_type=SecurityEventType.DEVICE_TRUSTED,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.audit.record(
            action="device.trusted", outcome="success", actor_user_id=user_id, target=device.id
        )
        return device

    async def revoke_device(self, *, user_id: str, device_id: str) -> TrustedDevice | None:
        device = await self.devices.revoke(user_id=user_id, device_id=device_id)
        if device is None:
            return None
        await self.record_event(event_type=SecurityEventType.DEVICE_REVOKED, user_id=user_id)
        await self.audit.record(
            action="device.revoked", outcome="success", actor_user_id=user_id, target=device_id
        )
        return device

    # -- password policy ---------------------------------------------

    async def get_policy(self, organization_id: str) -> tuple[PasswordPolicy, bool]:
        """Returns the effective policy and whether it was configured.

        The pair matters: the UI must distinguish "these are your rules"
        from "these are the defaults you have not overridden", and the
        security score only credits an organization that actually chose.
        """
        stored = await self.policies.get(organization_id)
        if stored is None:
            return DEFAULT_PASSWORD_POLICY, False
        return stored, True

    async def set_policy(
        self, *, organization_id: str, actor_user_id: str, policy: PasswordPolicy
    ) -> PasswordPolicy:
        updated = await self.policies.upsert(
            organization_id=organization_id,
            policy=policy,
            updated_by_user_id=actor_user_id,
        )
        await self.audit.record(
            action="password_policy.updated",
            outcome="success",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
        )
        return updated

    async def check_password(self, *, organization_id: str, password: str) -> list[str]:
        policy, _ = await self.get_policy(organization_id)
        return password_violations(password, policy)

    # -- score --------------------------------------------------------

    async def security_score(
        self,
        *,
        workspace_id: str,
        two_factor_enabled_members: int,
        total_members: int,
        ip_allowlist_configured: bool,
        sso_enforced: bool,
        password_policy_configured: bool,
        non_expiring_api_keys: int,
    ) -> SecurityScore:
        critical = await self.events.count_critical_since(
            workspace_id, since=datetime.now(UTC) - _INCIDENT_WINDOW
        )
        return compute_security_score(
            SecurityPosture(
                two_factor_enabled_members=two_factor_enabled_members,
                total_members=total_members,
                ip_allowlist_configured=ip_allowlist_configured,
                sso_enforced=sso_enforced,
                password_policy_configured=password_policy_configured,
                non_expiring_api_keys=non_expiring_api_keys,
                critical_events_last_30_days=critical,
            )
        )
