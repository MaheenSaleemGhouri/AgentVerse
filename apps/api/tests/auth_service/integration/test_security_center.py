"""Real-Postgres tests for the Security Center storage layer and for
API-key expiry enforcement.

Expiry in particular has to be tested against the real database: it is
enforced inside the authentication query, so a fake repository would
happily "pass" while the actual SQL let an expired credential through.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.domain.security import (
    PasswordPolicy,
    SecurityEventType,
    SecuritySeverity,
)
from agentverse_api.auth_service.infrastructure.models import User
from agentverse_api.auth_service.infrastructure.repositories import (
    SqlApiKeyRepository,
    SqlOrganizationRepository,
    SqlPasswordPolicyRepository,
    SqlSecurityEventRepository,
    SqlTrustedDeviceRepository,
    SqlWorkspaceRepository,
)

pytestmark = pytest.mark.integration


async def _make_user(session: AsyncSession, name: str) -> str:
    user_id = f"user-{name}"
    session.add(
        User(
            id=user_id,
            name=user_id,
            email=f"{name}@example.com",
            email_verified=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return user_id


# -- security events ------------------------------------------------------


async def test_severity_is_derived_from_the_event_type_not_supplied(
    db_session: AsyncSession, unique_name: str
) -> None:
    """Two callers recording the same event must produce the same
    severity, or the feed stops being sortable by urgency.
    """
    repo = SqlSecurityEventRepository(db_session)
    user_id = await _make_user(db_session, unique_name)
    await db_session.commit()

    event = await repo.record(
        user_id=user_id,
        workspace_id=None,
        organization_id=None,
        event_type=SecurityEventType.SUSPICIOUS_RAPID_FAILURES,
        ip_address="203.0.113.7",
        user_agent="pytest",
        metadata={"failures": "6"},
    )
    await db_session.commit()

    assert event.severity is SecuritySeverity.CRITICAL
    assert event.metadata == {"failures": "6"}


async def test_an_event_with_no_user_is_recordable(
    db_session: AsyncSession, unique_name: str
) -> None:
    """A failed login for an address matching no account still has to be
    recorded — dropping it would blind exactly the account-enumeration
    attempt it evidences.
    """
    repo = SqlSecurityEventRepository(db_session)

    event = await repo.record(
        user_id=None,
        workspace_id=None,
        organization_id=None,
        event_type=SecurityEventType.LOGIN_FAILED,
        ip_address="203.0.113.9",
        user_agent=None,
        metadata={"attempted_email": f"{unique_name}@example.com"},
    )
    await db_session.commit()

    assert event.user_id is None


async def test_events_come_back_newest_first_and_filter_by_severity(
    db_session: AsyncSession, unique_name: str
) -> None:
    repo = SqlSecurityEventRepository(db_session)
    user_id = await _make_user(db_session, unique_name)
    await db_session.commit()

    for event_type in (
        SecurityEventType.LOGIN_FAILED,
        SecurityEventType.ACCOUNT_LOCKED,
        SecurityEventType.SUSPICIOUS_RAPID_FAILURES,
    ):
        await repo.record(
            user_id=user_id,
            workspace_id=None,
            organization_id=None,
            event_type=event_type,
            ip_address=None,
            user_agent=None,
            metadata={},
        )
    await db_session.commit()

    everything = await repo.list_for_user(user_id, limit=10)
    assert len(everything) == 3
    assert everything[0].event_type is SecurityEventType.SUSPICIOUS_RAPID_FAILURES

    critical_only = await repo.list_for_user(user_id, limit=10, severity=SecuritySeverity.CRITICAL)
    assert [e.event_type for e in critical_only] == [SecurityEventType.SUSPICIOUS_RAPID_FAILURES]


async def test_the_event_type_check_constraint_rejects_an_unknown_value(
    db_session: AsyncSession,
) -> None:
    """The CHECK is the backstop if application validation is ever
    bypassed — asserted here rather than assumed from the migration.
    """
    with pytest.raises(Exception):  # noqa: B017 - driver-specific IntegrityError
        await db_session.execute(
            text(
                "INSERT INTO security_events (id, event_type, severity, metadata, created_at) "
                "VALUES (gen_random_uuid(), 'not.a.real.event', 'info', '{}'::jsonb, now())"
            )
        )
        await db_session.commit()
    await db_session.rollback()


# -- trusted devices ------------------------------------------------------


async def test_re_trusting_a_device_updates_it_rather_than_duplicating(
    db_session: AsyncSession, unique_name: str
) -> None:
    repo = SqlTrustedDeviceRepository(db_session)
    user_id = await _make_user(db_session, unique_name)
    await db_session.commit()

    first = await repo.upsert(
        user_id=user_id,
        device_fingerprint="fingerprint-abc",
        device_name="Laptop",
        user_agent="pytest",
        ip_address="203.0.113.1",
    )
    await db_session.commit()

    second = await repo.upsert(
        user_id=user_id,
        device_fingerprint="fingerprint-abc",
        device_name="Work Laptop",
        user_agent="pytest",
        ip_address="203.0.113.2",
    )
    await db_session.commit()

    assert second.id == first.id
    assert second.device_name == "Work Laptop"
    assert len(await repo.list_for_user(user_id)) == 1


async def test_re_trusting_a_revoked_device_un_revokes_it(
    db_session: AsyncSession, unique_name: str
) -> None:
    """Otherwise the row reads as trusted while still being refused."""
    repo = SqlTrustedDeviceRepository(db_session)
    user_id = await _make_user(db_session, unique_name)
    await db_session.commit()

    device = await repo.upsert(
        user_id=user_id,
        device_fingerprint="fingerprint-xyz",
        device_name=None,
        user_agent=None,
        ip_address=None,
    )
    await db_session.commit()

    revoked = await repo.revoke(user_id=user_id, device_id=device.id)
    await db_session.commit()
    assert revoked is not None
    assert not revoked.is_active

    again = await repo.upsert(
        user_id=user_id,
        device_fingerprint="fingerprint-xyz",
        device_name=None,
        user_agent=None,
        ip_address=None,
    )
    await db_session.commit()
    assert again.is_active


async def test_revoking_another_users_device_reads_as_not_found(
    db_session: AsyncSession, unique_name: str
) -> None:
    """Rule 11 — a device id alone must never be enough to act on
    someone else's device.
    """
    repo = SqlTrustedDeviceRepository(db_session)
    owner = await _make_user(db_session, unique_name)
    attacker = await _make_user(db_session, f"{unique_name}-other")
    await db_session.commit()

    device = await repo.upsert(
        user_id=owner,
        device_fingerprint="fingerprint-owned",
        device_name=None,
        user_agent=None,
        ip_address=None,
    )
    await db_session.commit()

    assert await repo.revoke(user_id=attacker, device_id=device.id) is None

    still_active = await repo.get(user_id=owner, device_fingerprint="fingerprint-owned")
    assert still_active is not None
    assert still_active.is_active


# -- password policy ------------------------------------------------------


async def test_password_policy_round_trips_and_updates_in_place(
    db_session: AsyncSession, unique_name: str
) -> None:
    user_id = await _make_user(db_session, unique_name)
    organization = await SqlOrganizationRepository(db_session).create_organization(
        name=unique_name, slug=unique_name, owner_user_id=user_id
    )
    await db_session.commit()

    repo = SqlPasswordPolicyRepository(db_session)
    assert await repo.get(organization.id) is None

    saved = await repo.upsert(
        organization_id=organization.id,
        policy=PasswordPolicy(
            min_length=16,
            require_uppercase=True,
            require_lowercase=True,
            require_number=True,
            require_symbol=True,
            max_age_days=90,
        ),
        updated_by_user_id=user_id,
    )
    await db_session.commit()
    assert saved.min_length == 16

    relaxed = await repo.upsert(
        organization_id=organization.id,
        policy=PasswordPolicy(
            min_length=12,
            require_uppercase=True,
            require_lowercase=True,
            require_number=True,
            require_symbol=False,
            max_age_days=None,
        ),
        updated_by_user_id=user_id,
    )
    await db_session.commit()

    assert relaxed.min_length == 12
    assert relaxed.max_age_days is None


async def test_a_policy_below_the_platform_floor_is_rejected_by_the_database(
    db_session: AsyncSession, unique_name: str
) -> None:
    """The CHECK exists so a policy can never make the product less safe
    than its own baseline, even if the API schema were bypassed.
    """
    user_id = await _make_user(db_session, unique_name)
    organization = await SqlOrganizationRepository(db_session).create_organization(
        name=unique_name, slug=unique_name, owner_user_id=user_id
    )
    await db_session.commit()

    with pytest.raises(Exception):  # noqa: B017 - driver-specific IntegrityError
        await db_session.execute(
            text(
                "INSERT INTO password_policies (organization_id, min_length, "
                "require_uppercase, require_lowercase, require_number, require_symbol, "
                "updated_at) VALUES (:org, 4, true, true, true, false, now())"
            ),
            {"org": organization.id},
        )
        await db_session.commit()
    await db_session.rollback()


# -- API key expiry -------------------------------------------------------


async def test_an_expired_key_does_not_authenticate(
    db_session: AsyncSession, unique_name: str
) -> None:
    """The whole point of storing an expiry is that the bearer path
    refuses the key. A stored-but-unenforced expiry would be worse than
    none, because it reads as a control that is not there.
    """
    user_id = await _make_user(db_session, unique_name)
    workspace = await SqlWorkspaceRepository(db_session).create_workspace(
        name=unique_name, slug=unique_name, owner_user_id=user_id
    )
    await db_session.commit()

    repo = SqlApiKeyRepository(db_session)
    expired = await repo.create_api_key(
        workspace_id=workspace.id,
        name="expired",
        key_prefix="av_live_exp",
        hashed_key=f"hash-expired-{unique_name}",
        created_by_user_id=user_id,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    live = await repo.create_api_key(
        workspace_id=workspace.id,
        name="live",
        key_prefix="av_live_ok",
        hashed_key=f"hash-live-{unique_name}",
        created_by_user_id=user_id,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    await db_session.commit()

    assert await repo.find_active_by_hash(expired.hashed_key) is None
    found = await repo.find_active_by_hash(live.hashed_key)
    assert found is not None
    assert found.id == live.id


async def test_use_count_increments_on_each_authentication(
    db_session: AsyncSession, unique_name: str
) -> None:
    user_id = await _make_user(db_session, unique_name)
    workspace = await SqlWorkspaceRepository(db_session).create_workspace(
        name=unique_name, slug=unique_name, owner_user_id=user_id
    )
    await db_session.commit()

    repo = SqlApiKeyRepository(db_session)
    key = await repo.create_api_key(
        workspace_id=workspace.id,
        name="counted",
        key_prefix="av_live_cnt",
        hashed_key=f"hash-counted-{unique_name}",
        created_by_user_id=user_id,
    )
    await db_session.commit()
    assert key.use_count == 0

    await repo.touch_last_used(key.id)
    await repo.touch_last_used(key.id)
    await db_session.commit()

    refreshed = await repo.get_api_key(key.id)
    assert refreshed is not None
    assert refreshed.use_count == 2
    assert refreshed.last_used_at is not None


async def test_non_expiring_keys_are_counted_for_the_security_score(
    db_session: AsyncSession, unique_name: str
) -> None:
    user_id = await _make_user(db_session, unique_name)
    workspace = await SqlWorkspaceRepository(db_session).create_workspace(
        name=unique_name, slug=unique_name, owner_user_id=user_id
    )
    await db_session.commit()

    repo = SqlApiKeyRepository(db_session)
    await repo.create_api_key(
        workspace_id=workspace.id,
        name="forever",
        key_prefix="av_live_fvr",
        hashed_key=f"hash-forever-{unique_name}",
        created_by_user_id=user_id,
    )
    await repo.create_api_key(
        workspace_id=workspace.id,
        name="bounded",
        key_prefix="av_live_bnd",
        hashed_key=f"hash-bounded-{unique_name}",
        created_by_user_id=user_id,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    await db_session.commit()

    assert await repo.count_non_expiring(workspace.id) == 1
