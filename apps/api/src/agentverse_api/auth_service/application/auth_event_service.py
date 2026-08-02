"""Records signup/login events into `audit_logs`.

Better Auth (apps/web) owns the actual signup/login flow (ADR-0005) —
this use case is invoked from a Better Auth server-side database hook
(`apps/web/lib/auth.ts`) calling back into `apps/api` so `audit_logs`
stays the single place every auth-relevant event lands (CLAUDE.md §10),
not split across two services' logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from agentverse_api.auth_service.application.audit_service import AuditService

# Increment 7 adds the security-relevant events beyond signup/login:
# a revoked session and a lockout are exactly what an incident review
# needs, and both originate in apps/web (Better Auth owns sessions and
# the password-verify path) rather than in apps/api.
AuthEventType = Literal[
    "auth.signup",
    "auth.login",
    "auth.session_revoked",
    "auth.account_locked",
]


@dataclass(slots=True)
class AuthEventService:
    audit: AuditService

    async def record_auth_event(self, *, event_type: AuthEventType, user_id: str) -> None:
        await self.audit.record(action=event_type, outcome="success", actor_user_id=user_id)
