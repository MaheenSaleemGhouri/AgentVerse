"""Real end-to-end RBAC tests through the actual FastAPI app + real
Postgres — the exact scenario `docs/roadmap.md` Phase 1 names as its
top risk: getting 403-vs-404 wrong on a single-workspace fixture that
never exercises the cross-tenant path. This suite always uses at least
two real workspaces (`decision-log.md` #22).

`get_current_identity` is overridden per test to a fixed user id — this
replaces real Better Auth JWT verification (covered separately by
`tests/auth_service/infrastructure/test_jwt_verifier.py`), not the
Postgres-backed authorization logic this suite actually exercises.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.infrastructure.models import AuditLog, User, Verification
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
    get_current_identity_optional,
)
from agentverse_api.infrastructure.db import get_db_session
from agentverse_api.main import create_app

pytestmark = pytest.mark.integration


async def _make_user(session: AsyncSession, user_id: str) -> None:
    session.add(
        User(
            id=user_id,
            name=user_id,
            email=f"{user_id}@example.com",
            email_verified=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    await session.commit()


@pytest.fixture
async def make_client(
    db_session: AsyncSession,
) -> AsyncIterator[Callable[[str], AsyncClient]]:
    """Returns a factory: `make_client("alice")` gives an `AsyncClient`
    hitting the real app, authenticated as "alice", sharing the same
    real `db_session` the test itself uses to set up fixture data.
    """
    clients: list[AsyncClient] = []

    async def db_session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    def factory(user_id: str) -> AsyncClient:
        app = create_app()
        app.dependency_overrides[get_db_session] = db_session_override
        app.dependency_overrides[get_current_identity] = lambda: user_id
        # `get_current_workspace` resolves the session through the
        # optional variant (an API key returns `None` there), so both
        # must be stubbed for a session-authenticated test client.
        app.dependency_overrides[get_current_identity_optional] = lambda: user_id
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        return client

    yield factory

    for client in clients:
        await client.aclose()


async def test_cross_workspace_access_is_404_not_403(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    user_a = f"user-a-{unique_name}"
    user_b = f"user-b-{unique_name}"
    await _make_user(db_session, user_a)
    await _make_user(db_session, user_b)

    client_a = make_client(user_a)
    client_b = make_client(user_b)

    create_a = await client_a.post("/api/v1/workspaces", json={"name": f"ws-a-{unique_name}"})
    assert create_a.status_code == 201
    workspace_a_id = create_a.json()["id"]

    create_b = await client_b.post("/api/v1/workspaces", json={"name": f"ws-b-{unique_name}"})
    assert create_b.status_code == 201
    workspace_b_id = create_b.json()["id"]

    # user_a (member of A only) requests B's resource — must be 404, not
    # 403: existence of a workspace user_a isn't in must not leak.
    response = await client_a.get(f"/api/v1/workspaces/{workspace_b_id}")
    assert response.status_code == 404

    # Sanity: user_a CAN reach their own workspace A.
    own = await client_a.get(f"/api/v1/workspaces/{workspace_a_id}")
    assert own.status_code == 200


async def test_member_denied_owner_only_action_returns_403_and_is_audited(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"owner-{unique_name}"
    member = f"member-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, member)

    owner_client = make_client(owner)
    member_client = make_client(member)

    create = await owner_client.post("/api/v1/workspaces", json={"name": f"ws-{unique_name}"})
    workspace_id = create.json()["id"]

    invite = await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"user_id": member, "role": "member"},
    )
    assert invite.status_code == 201

    # member attempts an owner-only action (changing someone's role).
    denied = await member_client.patch(
        f"/api/v1/workspaces/{workspace_id}/members/{owner}",
        json={"role": "admin"},
    )
    assert denied.status_code == 403

    # The denial itself is written to audit_logs (CLAUDE.md §10 — from
    # the enforcement point, not left to the caller to remember).
    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.workspace_id == workspace_id,
            AuditLog.action == "permission.denied",
            AuditLog.actor_user_id == member,
        )
    )
    denial_entries = result.scalars().all()
    assert len(denial_entries) == 1
    assert denial_entries[0].outcome == "denied"


async def test_owner_can_change_member_role(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"owner2-{unique_name}"
    member = f"member2-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, member)

    owner_client = make_client(owner)

    create = await owner_client.post("/api/v1/workspaces", json={"name": f"ws2-{unique_name}"})
    workspace_id = create.json()["id"]
    await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"user_id": member, "role": "member"},
    )

    response = await owner_client.patch(
        f"/api/v1/workspaces/{workspace_id}/members/{member}",
        json={"role": "admin"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"


async def test_audit_logs_route_is_admin_gated_and_returns_real_entries(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    """Increment 1: `GET .../audit-logs` — admin-gated (stricter than
    ordinary workspace reads), and the workspace-creation event itself
    is the first real row a caller sees.
    """
    owner = f"owner3-{unique_name}"
    member = f"member3-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, member)

    owner_client = make_client(owner)
    member_client = make_client(member)

    create = await owner_client.post("/api/v1/workspaces", json={"name": f"ws3-{unique_name}"})
    workspace_id = create.json()["id"]
    await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"user_id": member, "role": "member"},
    )

    denied = await member_client.get(f"/api/v1/workspaces/{workspace_id}/audit-logs")
    assert denied.status_code == 403

    allowed = await owner_client.get(f"/api/v1/workspaces/{workspace_id}/audit-logs")
    assert allowed.status_code == 200
    body = allowed.json()
    assert any(entry["action"] == "workspace.created" for entry in body["data"])
    assert all(entry["workspace_id"] == workspace_id for entry in body["data"])


async def test_workspace_settings_route_defaults_viewer_get_admin_patch(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    """Increment 2: `GET .../settings` is viewer-readable and returns
    documented defaults with no row yet; `PATCH` is admin-gated."""
    owner = f"owner4-{unique_name}"
    member = f"member4-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, member)

    owner_client = make_client(owner)
    member_client = make_client(member)

    create = await owner_client.post("/api/v1/workspaces", json={"name": f"ws4-{unique_name}"})
    workspace_id = create.json()["id"]
    await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"user_id": member, "role": "member"},
    )

    defaults = await member_client.get(f"/api/v1/workspaces/{workspace_id}/settings")
    assert defaults.status_code == 200
    assert defaults.json()["updated_at"] is None
    assert defaults.json()["retention_days"] is None

    denied = await member_client.patch(
        f"/api/v1/workspaces/{workspace_id}/settings", json={"retention_days": 30}
    )
    assert denied.status_code == 403

    allowed = await owner_client.patch(
        f"/api/v1/workspaces/{workspace_id}/settings", json={"retention_days": 30}
    )
    assert allowed.status_code == 200
    assert allowed.json()["retention_days"] == 30
    assert allowed.json()["updated_at"] is not None

    persisted = await member_client.get(f"/api/v1/workspaces/{workspace_id}/settings")
    assert persisted.json()["retention_days"] == 30


async def test_rotate_api_key_route_is_admin_gated_and_rejects_cross_workspace(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    """Increment 3: `POST .../api-keys/{id}/rotate` — admin-gated, and a
    key id from a different workspace 404s rather than rotating it."""
    owner = f"owner5-{unique_name}"
    member = f"member5-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, member)

    owner_client = make_client(owner)
    member_client = make_client(member)

    create_a = await owner_client.post("/api/v1/workspaces", json={"name": f"ws5a-{unique_name}"})
    workspace_a = create_a.json()["id"]
    create_b = await owner_client.post("/api/v1/workspaces", json={"name": f"ws5b-{unique_name}"})
    workspace_b = create_b.json()["id"]
    await owner_client.post(
        f"/api/v1/workspaces/{workspace_a}/members",
        json={"user_id": member, "role": "member"},
    )

    issued = await owner_client.post(
        f"/api/v1/workspaces/{workspace_a}/api-keys", json={"name": "ci"}
    )
    api_key_id = issued.json()["id"]

    denied = await member_client.post(
        f"/api/v1/workspaces/{workspace_a}/api-keys/{api_key_id}/rotate"
    )
    assert denied.status_code == 403

    cross_workspace = await owner_client.post(
        f"/api/v1/workspaces/{workspace_b}/api-keys/{api_key_id}/rotate"
    )
    assert cross_workspace.status_code == 404

    allowed = await owner_client.post(
        f"/api/v1/workspaces/{workspace_a}/api-keys/{api_key_id}/rotate"
    )
    assert allowed.status_code == 201
    rotated = allowed.json()
    assert rotated["rotated_from_id"] == api_key_id
    assert rotated["id"] != api_key_id
    assert "key" in rotated

    keys = await owner_client.get(f"/api/v1/workspaces/{workspace_a}/api-keys")
    original = next(k for k in keys.json() if k["id"] == api_key_id)
    assert original["revoked_at"] is not None


async def test_cross_organization_access_is_404_not_403(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    """Increment 4: mirrors `test_cross_workspace_access_is_404_not_403`
    for the new, fully independent organization RBAC chain (ADR-0011)."""
    user_a = f"org-user-a-{unique_name}"
    user_b = f"org-user-b-{unique_name}"
    await _make_user(db_session, user_a)
    await _make_user(db_session, user_b)

    client_a = make_client(user_a)
    client_b = make_client(user_b)

    create_a = await client_a.post("/api/v1/organizations", json={"name": f"org-a-{unique_name}"})
    assert create_a.status_code == 201
    org_a_id = create_a.json()["id"]

    response = await client_b.get(f"/api/v1/organizations/{org_a_id}")
    assert response.status_code == 404

    own = await client_a.get(f"/api/v1/organizations/{org_a_id}")
    assert own.status_code == 200


async def test_sole_organization_owner_cannot_be_removed_or_demoted(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"org-owner-{unique_name}"
    await _make_user(db_session, owner)
    owner_client = make_client(owner)

    create = await owner_client.post(
        "/api/v1/organizations", json={"name": f"org-solo-{unique_name}"}
    )
    org_id = create.json()["id"]

    demote = await owner_client.patch(
        f"/api/v1/organizations/{org_id}/members/{owner}", json={"role": "admin"}
    )
    assert demote.status_code == 409

    remove = await owner_client.delete(f"/api/v1/organizations/{org_id}/members/{owner}")
    assert remove.status_code == 409


async def test_attach_workspace_requires_both_org_admin_and_workspace_owner(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    """Increment 4's key composition: `require_org_role(ADMIN)` on the org
    AND `require_owner` on the target workspace, independently. An org
    admin who does not own the workspace cannot attach it."""
    org_owner = f"org-owner2-{unique_name}"
    workspace_owner = f"ws-owner2-{unique_name}"
    await _make_user(db_session, org_owner)
    await _make_user(db_session, workspace_owner)

    org_client = make_client(org_owner)
    workspace_client = make_client(workspace_owner)

    create_org = await org_client.post(
        "/api/v1/organizations", json={"name": f"org-attach-{unique_name}"}
    )
    org_id = create_org.json()["id"]
    create_ws = await workspace_client.post(
        "/api/v1/workspaces", json={"name": f"ws-attach-{unique_name}"}
    )
    workspace_id = create_ws.json()["id"]
    # org_owner is a real member of the workspace, but only at `member`
    # role — below `require_owner`'s floor. This isolates the case this
    # test targets (known member, insufficient role → 403) from the
    # unrelated non-member case (unknown to the workspace → 404, already
    # covered by `test_cross_workspace_access_is_404_not_403`).
    await workspace_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"user_id": org_owner, "role": "member"},
    )

    # org_owner administers the org and is a workspace member, but not its
    # owner — 403 from the workspace-side `require_owner` check.
    denied = await org_client.post(f"/api/v1/organizations/{org_id}/workspaces/{workspace_id}")
    assert denied.status_code == 403

    # workspace_owner owns the workspace but isn't even a member of the
    # org — 404 from the org-side `require_org_role` check.
    denied_other_way = await workspace_client.post(
        f"/api/v1/organizations/{org_id}/workspaces/{workspace_id}"
    )
    assert denied_other_way.status_code == 404


async def test_attach_detach_and_delete_organization_leave_workspace_rbac_untouched(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    """End-to-end acceptance test for ADR-0011's core invariant: attaching
    a workspace to an organization changes nothing about who can access
    that workspace, and deleting the organization only detaches it."""
    owner = f"both-owner-{unique_name}"
    workspace_member = f"ws-member-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, workspace_member)

    owner_client = make_client(owner)

    create_org = await owner_client.post(
        "/api/v1/organizations", json={"name": f"org-e2e-{unique_name}"}
    )
    org_id = create_org.json()["id"]
    create_ws = await owner_client.post(
        "/api/v1/workspaces", json={"name": f"ws-e2e-{unique_name}"}
    )
    workspace_id = create_ws.json()["id"]
    await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"user_id": workspace_member, "role": "member"},
    )

    attach = await owner_client.post(f"/api/v1/organizations/{org_id}/workspaces/{workspace_id}")
    assert attach.status_code == 204

    attached_workspace = await owner_client.get(f"/api/v1/workspaces/{workspace_id}")
    assert attached_workspace.json()["organization_id"] == org_id

    # Attaching changed nothing about workspace membership.
    members = await owner_client.get(f"/api/v1/workspaces/{workspace_id}/members")
    member_ids = {member["user_id"] for member in members.json()}
    assert member_ids == {owner, workspace_member}

    detach = await owner_client.delete(f"/api/v1/organizations/{org_id}/workspaces/{workspace_id}")
    assert detach.status_code == 204
    detached_workspace = await owner_client.get(f"/api/v1/workspaces/{workspace_id}")
    assert detached_workspace.json()["organization_id"] is None

    # Re-attach, then delete the organization outright — the workspace
    # must survive, merely detached.
    await owner_client.post(f"/api/v1/organizations/{org_id}/workspaces/{workspace_id}")
    delete_org = await owner_client.delete(f"/api/v1/organizations/{org_id}")
    assert delete_org.status_code == 204

    surviving_workspace = await owner_client.get(f"/api/v1/workspaces/{workspace_id}")
    assert surviving_workspace.status_code == 200
    assert surviving_workspace.json()["organization_id"] is None
    surviving_members = await owner_client.get(f"/api/v1/workspaces/{workspace_id}/members")
    assert {m["user_id"] for m in surviving_members.json()} == {owner, workspace_member}


async def test_invite_by_email_adds_an_existing_user_directly(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    """Increment 5: inviting an email that matches a real account is
    immediate membership — no token, no email dispatch."""
    owner = f"inv-owner-{unique_name}"
    invitee = f"inv-existing-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, invitee)

    owner_client = make_client(owner)
    invitee_client = make_client(invitee)

    create = await owner_client.post("/api/v1/workspaces", json={"name": f"inv-ws-{unique_name}"})
    workspace_id = create.json()["id"]

    response = await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/invitations",
        json={"email": f"{invitee}@example.com", "role": "member"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "added"

    now_a_member = await invitee_client.get(f"/api/v1/workspaces/{workspace_id}")
    assert now_a_member.status_code == 200


async def test_invite_by_email_for_an_unknown_address_requires_admin_and_returns_invited(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"inv-owner2-{unique_name}"
    member = f"inv-member2-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, member)

    owner_client = make_client(owner)
    member_client = make_client(member)

    create = await owner_client.post("/api/v1/workspaces", json={"name": f"inv-ws2-{unique_name}"})
    workspace_id = create.json()["id"]
    await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"user_id": member, "role": "member"},
    )

    denied = await member_client.post(
        f"/api/v1/workspaces/{workspace_id}/invitations",
        json={"email": "unknown-person@example.com", "role": "member"},
    )
    assert denied.status_code == 403

    allowed = await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/invitations",
        json={"email": "unknown-person@example.com", "role": "member"},
    )
    assert allowed.status_code == 201
    assert allowed.json()["status"] == "invited"


async def test_accept_invite_end_to_end_via_the_real_token(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    """The full round trip: invite an unregistered email, capture the
    real token from the real `verifications` row (standing in for
    clicking the emailed link), accept as the now-registered user, and
    confirm a second acceptance attempt is rejected as consumed."""
    owner = f"inv-owner3-{unique_name}"
    invitee = f"inv-newcomer-{unique_name}"
    await _make_user(db_session, owner)

    owner_client = make_client(owner)

    create = await owner_client.post("/api/v1/workspaces", json={"name": f"inv-ws3-{unique_name}"})
    workspace_id = create.json()["id"]

    invite = await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/invitations",
        json={"email": f"{invitee}@example.com", "role": "admin"},
    )
    assert invite.status_code == 201
    assert invite.json()["status"] == "invited"

    result = await db_session.execute(
        select(Verification).where(
            Verification.identifier.like(f"workspace-invite:%:{invitee}@example.com")
        )
    )
    row = result.scalars().one()
    token = row.value

    # The invitee signs up only now — the email had no account when invited.
    await _make_user(db_session, invitee)
    invitee_client = make_client(invitee)

    accept = await invitee_client.post("/api/v1/invitations/accept", json={"token": token})
    assert accept.status_code == 200
    assert accept.json() == {"target_type": "workspace", "target_id": workspace_id}

    members = await owner_client.get(f"/api/v1/workspaces/{workspace_id}/members")
    accepted_member = next(m for m in members.json() if m["user_id"] == invitee)
    assert accepted_member["role"] == "admin"

    replay = await invitee_client.post("/api/v1/invitations/accept", json={"token": token})
    assert replay.status_code == 400


async def test_accept_invite_rejects_a_different_users_email(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"inv-owner4-{unique_name}"
    invitee = f"inv-target4-{unique_name}"
    interloper = f"inv-interloper4-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, invitee)
    await _make_user(db_session, interloper)

    owner_client = make_client(owner)
    interloper_client = make_client(interloper)

    create = await owner_client.post("/api/v1/workspaces", json={"name": f"inv-ws4-{unique_name}"})
    workspace_id = create.json()["id"]

    # invitee already has an account, so this is added directly — force a
    # real token instead by inviting an address with no account yet, then
    # having a *different* real account try to accept it.
    invite = await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/invitations",
        json={"email": f"unclaimed-{unique_name}@example.com", "role": "member"},
    )
    assert invite.json()["status"] == "invited"

    result = await db_session.execute(
        select(Verification).where(
            Verification.identifier.like(f"workspace-invite:%:unclaimed-{unique_name}@example.com")
        )
    )
    token = result.scalars().one().value

    denied = await interloper_client.post("/api/v1/invitations/accept", json={"token": token})
    assert denied.status_code == 400
