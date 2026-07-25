from agentverse_api.auth_service.application.api_key_service import ApiKeyService
from agentverse_api.auth_service.application.audit_service import AuditService
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

    await service.revoke_api_key(api_key_id=issued.entity.id, actor_user_id="u1")

    assert key_repo.keys[issued.entity.id].revoked_at is not None
    assert not key_repo.keys[issued.entity.id].is_active
    assert any(entry.action == "api_key.revoked" for entry in audit_repo.entries)


async def test_list_api_keys_scoped_to_workspace() -> None:
    service, _key_repo, _audit_repo = _service()
    await service.issue_api_key(workspace_id="ws1", name="a", created_by_user_id="u1")
    await service.issue_api_key(workspace_id="ws2", name="b", created_by_user_id="u1")

    keys = await service.list_api_keys("ws1")

    assert len(keys) == 1
    assert keys[0].workspace_id == "ws1"
