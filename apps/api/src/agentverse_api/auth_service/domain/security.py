"""Security-posture domain logic: event taxonomy, password policy, and
the security score.

Everything here is pure — no I/O, no framework imports — so the rules
that decide whether a password is acceptable and how a workspace scores
can be unit-tested directly (CLAUDE.md §3, Testability). The repository
and route layers supply the facts; this module decides what they mean.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SecuritySeverity(StrEnum):
    """How much attention an event deserves.

    Deliberately three levels, not five: an operator triaging a feed
    needs "ignore / look / act now", and finer gradations only push the
    judgement call from the reader to the author.
    """

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SecurityEventType(StrEnum):
    """Security signals about an *account*, distinct from `audit_logs`.

    The two are not duplicates and are deliberately not merged:
    `audit_logs` answers "who did what inside this workspace" and is
    workspace-scoped and append-only for compliance; a security event
    answers "what happened to this identity's security posture" and is
    frequently user-scoped with no workspace at all (a failed login
    happens before any workspace is resolved). Merging them would force
    a nullable workspace onto the compliance log and a workspace filter
    onto questions that have no workspace.
    """

    LOGIN_NEW_DEVICE = "login.new_device"
    LOGIN_FAILED = "login.failed"
    ACCOUNT_LOCKED = "account.locked"
    PASSWORD_CHANGED = "password.changed"
    TWO_FACTOR_ENABLED = "two_factor.enabled"
    TWO_FACTOR_DISABLED = "two_factor.disabled"
    DEVICE_TRUSTED = "device.trusted"
    DEVICE_REVOKED = "device.revoked"
    SUSPICIOUS_IP = "suspicious.ip"
    SUSPICIOUS_RAPID_FAILURES = "suspicious.rapid_failures"


#: Severity is a property of the event type, not something a caller
#: picks — otherwise the same event lands at different severities
#: depending on which code path recorded it, and the feed stops being
#: sortable by urgency.
_SEVERITY_BY_TYPE: dict[SecurityEventType, SecuritySeverity] = {
    SecurityEventType.LOGIN_NEW_DEVICE: SecuritySeverity.INFO,
    SecurityEventType.LOGIN_FAILED: SecuritySeverity.INFO,
    SecurityEventType.ACCOUNT_LOCKED: SecuritySeverity.WARNING,
    SecurityEventType.PASSWORD_CHANGED: SecuritySeverity.INFO,
    SecurityEventType.TWO_FACTOR_ENABLED: SecuritySeverity.INFO,
    SecurityEventType.TWO_FACTOR_DISABLED: SecuritySeverity.WARNING,
    SecurityEventType.DEVICE_TRUSTED: SecuritySeverity.INFO,
    SecurityEventType.DEVICE_REVOKED: SecuritySeverity.INFO,
    SecurityEventType.SUSPICIOUS_IP: SecuritySeverity.WARNING,
    SecurityEventType.SUSPICIOUS_RAPID_FAILURES: SecuritySeverity.CRITICAL,
}


def severity_for(event_type: SecurityEventType) -> SecuritySeverity:
    return _SEVERITY_BY_TYPE[event_type]


# ---------------------------------------------------------------------------
# Password policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PasswordPolicy:
    """An organization's password requirements.

    `min_length` floors at 8 rather than 0 in the schema layer: a policy
    row that weakens passwords below the platform baseline would be a
    policy feature that makes the product less safe, which is not a
    setting worth offering.
    """

    min_length: int
    require_uppercase: bool
    require_lowercase: bool
    require_number: bool
    require_symbol: bool
    #: `None` means passwords never expire. Forced rotation is off by
    #: default because periodic expiry is no longer recommended practice
    #: (NIST SP 800-63B) — it is offered for organizations whose own
    #: compliance regime still requires it, not as a default.
    max_age_days: int | None


#: What every organization gets before anyone configures anything. Not
#: an empty/permissive policy — an unconfigured organization should
#: still be on a sane baseline.
DEFAULT_PASSWORD_POLICY = PasswordPolicy(
    min_length=12,
    require_uppercase=True,
    require_lowercase=True,
    require_number=True,
    require_symbol=False,
    max_age_days=None,
)

_SYMBOLS = set("!@#$%^&*()-_=+[]{};:'\",.<>/?\\|`~")


def password_violations(password: str, policy: PasswordPolicy) -> list[str]:
    """Every way `password` fails `policy`, as human-readable reasons.

    Returns all violations rather than the first, so a user fixing their
    password is told everything at once instead of discovering the next
    rule on each retry.
    """
    violations: list[str] = []
    if len(password) < policy.min_length:
        violations.append(f"Must be at least {policy.min_length} characters.")
    if policy.require_uppercase and not any(c.isupper() for c in password):
        violations.append("Must include an uppercase letter.")
    if policy.require_lowercase and not any(c.islower() for c in password):
        violations.append("Must include a lowercase letter.")
    if policy.require_number and not any(c.isdigit() for c in password):
        violations.append("Must include a number.")
    if policy.require_symbol and not any(c in _SYMBOLS for c in password):
        violations.append("Must include a symbol.")
    return violations


# ---------------------------------------------------------------------------
# Security score
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SecurityPosture:
    """The facts a score is computed from. Gathered by the application
    layer; scored here.
    """

    two_factor_enabled_members: int
    total_members: int
    ip_allowlist_configured: bool
    sso_enforced: bool
    password_policy_configured: bool
    #: Keys with no expiry are counted, not just listed: a
    #: never-expiring credential is the finding, regardless of how many
    #: there are.
    non_expiring_api_keys: int
    critical_events_last_30_days: int


@dataclass(frozen=True, slots=True)
class ScoreFactor:
    """One contributing line item, so the score is explainable rather
    than a bare number the user cannot act on.
    """

    key: str
    label: str
    earned: int
    possible: int
    #: What to do about it, or `None` when nothing is wrong.
    remediation: str | None


@dataclass(frozen=True, slots=True)
class SecurityScore:
    score: int
    grade: str
    factors: list[ScoreFactor]


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def compute_security_score(posture: SecurityPosture) -> SecurityScore:
    """Score a workspace's security posture out of 100.

    The weights are a deliberate ranking, not arbitrary: two-factor
    coverage is the single largest control against credential theft, so
    it carries the most weight; a never-expiring API key and recent
    critical events are penalties rather than missing bonuses, because
    they represent something actively wrong rather than something not
    yet done.
    """
    factors: list[ScoreFactor] = []

    # Two-factor coverage — proportional, so partial rollout earns
    # partial credit rather than nothing.
    two_factor_possible = 40
    if posture.total_members == 0:
        two_factor_earned = two_factor_possible
        two_factor_remediation = None
    else:
        covered = posture.two_factor_enabled_members / posture.total_members
        two_factor_earned = round(two_factor_possible * covered)
        uncovered = posture.total_members - posture.two_factor_enabled_members
        two_factor_remediation = (
            None
            if uncovered == 0
            else f"{uncovered} of {posture.total_members} members have not enabled two-factor."
        )
    factors.append(
        ScoreFactor(
            key="two_factor",
            label="Two-factor authentication",
            earned=two_factor_earned,
            possible=two_factor_possible,
            remediation=two_factor_remediation,
        )
    )

    factors.append(
        ScoreFactor(
            key="sso",
            label="Single sign-on enforced",
            earned=20 if posture.sso_enforced else 0,
            possible=20,
            remediation=None
            if posture.sso_enforced
            else "Configure SSO so access follows your identity provider.",
        )
    )

    factors.append(
        ScoreFactor(
            key="password_policy",
            label="Password policy configured",
            earned=15 if posture.password_policy_configured else 0,
            possible=15,
            remediation=None
            if posture.password_policy_configured
            else "Set a password policy; the platform default applies until you do.",
        )
    )

    factors.append(
        ScoreFactor(
            key="ip_allowlist",
            label="IP allowlist configured",
            earned=10 if posture.ip_allowlist_configured else 0,
            possible=10,
            remediation=None
            if posture.ip_allowlist_configured
            else "Restrict access to known networks if your team works from fixed locations.",
        )
    )

    # Penalties. Expressed as a factor that starts full and loses points,
    # so the UI can render every line the same way.
    api_key_possible = 10
    api_key_earned = api_key_possible if posture.non_expiring_api_keys == 0 else 0
    factors.append(
        ScoreFactor(
            key="api_key_expiry",
            label="API keys expire",
            earned=api_key_earned,
            possible=api_key_possible,
            remediation=None
            if posture.non_expiring_api_keys == 0
            else f"{posture.non_expiring_api_keys} API key(s) never expire.",
        )
    )

    incident_possible = 5
    incident_earned = incident_possible if posture.critical_events_last_30_days == 0 else 0
    factors.append(
        ScoreFactor(
            key="recent_incidents",
            label="No critical events in 30 days",
            earned=incident_earned,
            possible=incident_possible,
            remediation=None
            if posture.critical_events_last_30_days == 0
            else (
                f"{posture.critical_events_last_30_days} critical security event(s) "
                "in the last 30 days."
            ),
        )
    )

    score = sum(factor.earned for factor in factors)
    return SecurityScore(score=score, grade=_grade(score), factors=factors)
