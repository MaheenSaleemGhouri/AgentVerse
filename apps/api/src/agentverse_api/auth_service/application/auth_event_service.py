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
# the password-verify path) rather than in apps/api. Phase 12 adds a
# failed-login event (every failed attempt, not only the one that trips
# the lock) and a distinct SSO-login event, closing the audit-coverage
# gap a Phase 12 review found: only login *success* was ever recorded.
AuthEventType = Literal[
    "auth.signup",
    "auth.login",
    "auth.login_failed",
    "auth.sso_login",
    "auth.session_revoked",
    "auth.account_locked",
]

#: The only two events reported with a non-"success" outcome — every
#: other event in `AuthEventType` is, by construction, only ever fired
#: when the thing it names actually happened.
_FAILURE_EVENTS: frozenset[AuthEventType] = frozenset({"auth.login_failed"})


@dataclass(slots=True)
class AuthEventService:
    audit: AuditService

    async def record_auth_event(self, *, event_type: AuthEventType, user_id: str) -> None:
        outcome = "failure" if event_type in _FAILURE_EVENTS else "success"
        await self.audit.record(action=event_type, outcome=outcome, actor_user_id=user_id)
