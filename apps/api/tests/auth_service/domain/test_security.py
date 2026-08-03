"""Unit tests for the pure security-posture logic.

Password validation and scoring are pure functions precisely so they can
be tested exhaustively without a database (CLAUDE.md §3) — every case
here is a direct call, no fixtures, no I/O.
"""

from __future__ import annotations

import pytest

from agentverse_api.auth_service.domain.security import (
    DEFAULT_PASSWORD_POLICY,
    PasswordPolicy,
    SecurityEventType,
    SecurityPosture,
    SecuritySeverity,
    compute_security_score,
    password_violations,
    severity_for,
)

# -- severity mapping -----------------------------------------------------


def test_every_event_type_has_a_severity() -> None:
    """A new event type must not be able to ship without one — an event
    with no severity would sort unpredictably in the feed.
    """
    for event_type in SecurityEventType:
        assert isinstance(severity_for(event_type), SecuritySeverity)


def test_rapid_failures_is_the_only_critical_signal() -> None:
    critical = {
        event_type
        for event_type in SecurityEventType
        if severity_for(event_type) is SecuritySeverity.CRITICAL
    }
    assert critical == {SecurityEventType.SUSPICIOUS_RAPID_FAILURES}


# -- password policy ------------------------------------------------------


def test_default_policy_accepts_a_strong_password() -> None:
    assert password_violations("CorrectHorse7Battery", DEFAULT_PASSWORD_POLICY) == []


def test_every_violation_is_reported_at_once_not_just_the_first() -> None:
    """A user fixing their password should be told all the rules, not
    discover the next one on each retry.
    """
    violations = password_violations("abc", DEFAULT_PASSWORD_POLICY)

    assert len(violations) == 3
    assert any("12 characters" in v for v in violations)
    assert any("uppercase" in v for v in violations)
    assert any("number" in v for v in violations)


@pytest.mark.parametrize(
    ("password", "expected_ok"),
    [
        ("Sufficient1Length!", True),
        ("nouppercase1here!!!", False),
        ("NOLOWERCASE1HERE!!!", False),
        ("NoDigitsInHereAtAll!", False),
    ],
)
def test_individual_character_class_rules(password: str, expected_ok: bool) -> None:
    policy = PasswordPolicy(
        min_length=12,
        require_uppercase=True,
        require_lowercase=True,
        require_number=True,
        require_symbol=False,
        max_age_days=None,
    )
    assert (password_violations(password, policy) == []) is expected_ok


def test_symbol_requirement_is_off_by_default_but_enforced_when_set() -> None:
    without_symbol = "NoSymbolsHere123"
    assert password_violations(without_symbol, DEFAULT_PASSWORD_POLICY) == []

    strict = PasswordPolicy(
        min_length=12,
        require_uppercase=True,
        require_lowercase=True,
        require_number=True,
        require_symbol=True,
        max_age_days=None,
    )
    assert password_violations(without_symbol, strict) != []
    assert password_violations("NoSymbolsHere123!", strict) == []


# -- security score -------------------------------------------------------


def _posture(**overrides: object) -> SecurityPosture:
    base = {
        "two_factor_enabled_members": 0,
        "total_members": 10,
        "ip_allowlist_configured": False,
        "sso_enforced": False,
        "password_policy_configured": False,
        "non_expiring_api_keys": 0,
        "critical_events_last_30_days": 0,
    }
    base.update(overrides)
    return SecurityPosture(**base)  # type: ignore[arg-type]


def test_a_fully_hardened_workspace_scores_100() -> None:
    score = compute_security_score(
        _posture(
            two_factor_enabled_members=10,
            ip_allowlist_configured=True,
            sso_enforced=True,
            password_policy_configured=True,
        )
    )

    assert score.score == 100
    assert score.grade == "A"
    # Nothing is wrong, so nothing has a remediation to offer.
    assert all(factor.remediation is None for factor in score.factors)


def test_two_factor_coverage_is_proportional_not_all_or_nothing() -> None:
    """Half the team on two-factor must score better than none — an
    all-or-nothing rule gives a rollout no visible progress.
    """
    none = compute_security_score(_posture(two_factor_enabled_members=0))
    half = compute_security_score(_posture(two_factor_enabled_members=5))
    full = compute_security_score(_posture(two_factor_enabled_members=10))

    assert none.score < half.score < full.score


def test_an_empty_workspace_is_not_penalised_for_two_factor() -> None:
    """Zero members means zero uncovered members. Dividing by zero, or
    scoring it as 0% coverage, would tell a brand-new workspace it has a
    problem it cannot act on.
    """
    score = compute_security_score(_posture(two_factor_enabled_members=0, total_members=0))

    two_factor = next(f for f in score.factors if f.key == "two_factor")
    assert two_factor.earned == two_factor.possible
    assert two_factor.remediation is None


def test_score_is_the_sum_of_its_factors() -> None:
    """The number and the breakdown must agree — a score the factors
    cannot explain is one a user cannot act on.
    """
    score = compute_security_score(
        _posture(two_factor_enabled_members=3, sso_enforced=True, non_expiring_api_keys=2)
    )

    assert score.score == sum(factor.earned for factor in score.factors)


def test_non_expiring_keys_and_recent_incidents_cost_points_and_explain_why() -> None:
    clean = compute_security_score(_posture(two_factor_enabled_members=10))
    with_findings = compute_security_score(
        _posture(
            two_factor_enabled_members=10,
            non_expiring_api_keys=3,
            critical_events_last_30_days=1,
        )
    )

    assert with_findings.score < clean.score

    api_key_factor = next(f for f in with_findings.factors if f.key == "api_key_expiry")
    assert api_key_factor.remediation is not None
    assert "3" in api_key_factor.remediation

    incident_factor = next(f for f in with_findings.factors if f.key == "recent_incidents")
    assert incident_factor.remediation is not None


def test_grade_reflects_the_score_across_the_range() -> None:
    """Spot-checked against the actual weights rather than a guess:
    two-factor alone is 40 + 10 (keys) + 5 (no incidents) = 55, a D. It
    takes SSO and a password policy on top to reach an A.
    """
    two_factor_only = compute_security_score(_posture(two_factor_enabled_members=10))
    assert two_factor_only.score == 55
    assert two_factor_only.grade == "D"

    nothing = compute_security_score(_posture(non_expiring_api_keys=1))
    assert nothing.grade == "F"

    everything = compute_security_score(
        _posture(
            two_factor_enabled_members=10,
            sso_enforced=True,
            password_policy_configured=True,
            ip_allowlist_configured=True,
        )
    )
    assert everything.grade == "A"
