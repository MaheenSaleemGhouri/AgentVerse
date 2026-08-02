import pytest

from agentverse_api.auth_service.application.api_key_service import ApiKeyService
from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.api_key_scope import ApiKeyScope
from agentverse_api.auth_service.domain.exceptions import ApiKeyNotFoundError
from tests.fakes.auth_service_repositories import FakeApiKeyRepository, FakeAuditLogRepository


def _service() -> tuple[ApiKeyService, FakeApiKeyRepository, FakeAuditLogRepository]:
    key_repo = FakeApiKeyRepository()
    audit_repo = FakeAuditLogRepository()
    return (
        ApiKeyService(api_keys=key_repo, audit=AuditService(audit_logs=audit_repo)),
        key_repo,
        audit_repo,
    )


async def test_issue_api_key_returns_plaintext_exactly_once() -> None:
    service, key_repo, audit_repo = _service()

    issued = await service.issue_api_key(workspace_id="ws1", name="CI key", created_by_user_id="u1")

    assert issued.plaintext_key.startswith("av_live_")
    # Stored form must never equal (or contain) the plaintext secret.
    assert issued.entity.hashed_key != issued.plaintext_key
    assert issued.plaintext_key not in issued.entity.hashed_key
    assert any(entry.action == "api_key.issued" for entry in audit_repo.entries)
    stored = key_repo.keys[issued.entity.id]
    assert stored.hashed_key == issued.entity.hashed_key


async def test_issuing_twice_produces_different_secrets_and_hashes() -> None:
    service, _key_repo, _audit_repo = _service()

    first = await service.issue_api_key(workspace_id="ws1", name="a", created_by_user_id="u1")
    second = await service.issue_api_key(workspace_id="ws1", name="b", created_by_user_id="u1")

    assert first.plaintext_key != second.plaintext_key
    assert first.entity.hashed_key != second.entity.hashed_key


async def test_revoke_api_key_sets_revoked_at_and_audits() -> None:
    service, key_repo, audit_repo = _service()
    issued = await service.issue_api_key(
        workspace_id="ws1", name="to revoke", created_by_user_id="u1"
    )
    assert issued.entity.is_active

    await service.revoke_api_key(
        workspace_id="ws1", api_key_id=issued.entity.id, actor_user_id="u1"
    )

    assert key_repo.keys[issued.entity.id].revoked_at is not None
    assert not key_repo.keys[issued.entity.id].is_active
    assert any(entry.action == "api_key.revoked" for entry in audit_repo.entries)


async def test_revoke_refuses_a_key_owned_by_another_workspace() -> None:
    service, key_repo, _audit_repo = _service()
    issued = await service.issue_api_key(
        workspace_id="ws1", name="theirs", created_by_user_id="u1"
    )

    with pytest.raises(ApiKeyNotFoundError):
        await service.revoke_api_key(
            workspace_id="ws2", api_key_id=issued.entity.id, actor_user_id="intruder"
        )

    assert key_repo.keys[issued.entity.id].is_active


async def test_authenticate_resolves_an_active_key_and_rejects_the_rest() -> None:
    service, key_repo, _audit_repo = _service()
    issued = await service.issue_api_key(
        workspace_id="ws1", name="live", created_by_user_id="u1"
    )

    resolved = await service.authenticate(issued.plaintext_key)
    assert resolved is not None
    assert resolved.id == issued.entity.id
    # The returned entity is the pre-touch snapshot; the recorded usage
    # is asserted where it actually lands.
    assert key_repo.keys[issued.entity.id].last_used_at is not None

    assert await service.authenticate("not-even-an-agentverse-key") is None
    assert await service.authenticate("av_live_wrong") is None

    await service.revoke_api_key(
        workspace_id="ws1", api_key_id=issued.entity.id, actor_user_id="u1"
    )
    assert await service.authenticate(issued.plaintext_key) is None


async def test_list_api_keys_scoped_to_workspace() -> None:
    service, _key_repo, _audit_repo = _service()
    await service.issue_api_key(workspace_id="ws1", name="a", created_by_user_id="u1")
    await service.issue_api_key(workspace_id="ws2", name="b", created_by_user_id="u1")

    keys = await service.list_api_keys("ws1")

    assert len(keys) == 1
    assert keys[0].workspace_id == "ws1"


async def test_issue_api_key_stores_the_requested_scope_and_tier() -> None:
    service, _key_repo, _audit_repo = _service()

    issued = await service.issue_api_key(
        workspace_id="ws1",
        name="ci",
        created_by_user_id="u1",
        scope=ApiKeyScope.READ_ONLY,
        tier="premium",
    )

    assert issued.entity.scope is ApiKeyScope.READ_ONLY
    assert issued.entity.tier == "premium"


async def test_rotate_api_key_revokes_the_old_key_and_links_the_new_one() -> None:
    service, key_repo, audit_repo = _service()
    original = await service.issue_api_key(
        workspace_id="ws1",
        name="ci",
        created_by_user_id="u1",
        scope=ApiKeyScope.READ_ONLY,
        tier="premium",
    )

    rotated = await service.rotate_api_key(
        workspace_id="ws1", api_key_id=original.entity.id, actor_user_id="u2"
    )

    assert not key_repo.keys[original.entity.id].is_active
    assert rotated.entity.is_active
    assert rotated.entity.rotated_from_id == original.entity.id
    # Same name/scope/tier carried over — a rotation is a credential
    # swap, not a reconfiguration.
    assert rotated.entity.name == original.entity.name
    assert rotated.entity.scope is ApiKeyScope.READ_ONLY
    assert rotated.entity.tier == "premium"
    assert rotated.plaintext_key != original.plaintext_key
    assert any(
        entry.action == "api_key.rotated"
        and entry.metadata.get("rotated_from_id") == original.entity.id
        for entry in audit_repo.entries
    )


async def test_rotate_api_key_raises_for_an_unknown_key() -> None:
    service, _key_repo, _audit_repo = _service()

    with pytest.raises(ApiKeyNotFoundError):
        await service.rotate_api_key(
            workspace_id="ws1", api_key_id="nonexistent", actor_user_id="u1"
        )


async def test_rotate_api_key_raises_for_a_key_in_another_workspace() -> None:
    """Same error as "doesn't exist" — a cross-workspace id must not be
    distinguishable from one that simply isn't real (Rule 11)."""
    service, _key_repo, _audit_repo = _service()
    issued = await service.issue_api_key(workspace_id="ws1", name="ci", created_by_user_id="u1")

    with pytest.raises(ApiKeyNotFoundError):
        await service.rotate_api_key(
            workspace_id="ws2", api_key_id=issued.entity.id, actor_user_id="u1"
        )
