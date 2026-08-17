"""End-to-end proof of Phase 11's literal acceptance criterion: a
referral code resolved through `GET .../billing/referrals` and passed
back through `POST /api/v1/workspaces` produces a real, attributed
`billing_referrals` row — closing the gap the audit found, where
`CreditService.attribute()` existed but had no production call site.

Real Postgres, real app, two real workspaces (`decision-log.md` #22) —
mirrors `test_rbac_routes.py`'s `make_client` pattern.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.infrastructure.models import User
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
    clients: list[AsyncClient] = []

    async def db_session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    def factory(user_id: str) -> AsyncClient:
        app = create_app()
        app.dependency_overrides[get_db_session] = db_session_override
        app.dependency_overrides[get_current_identity] = lambda: user_id
        app.dependency_overrides[get_current_identity_optional] = lambda: user_id
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        return client

    yield factory

    for client in clients:
        await client.aclose()


async def test_a_referral_code_attributes_the_new_workspace_end_to_end(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    referrer_user = f"referrer-{unique_name}"
    referred_user = f"referred-{unique_name}"
    await _make_user(db_session, referrer_user)
    await _make_user(db_session, referred_user)

    referrer_client = make_client(referrer_user)
    referred_client = make_client(referred_user)

    create_referrer = await referrer_client.post(
        "/api/v1/workspaces", json={"name": f"referrer-ws-{unique_name}"}
    )
    assert create_referrer.status_code == 201
    referrer_workspace_id = create_referrer.json()["id"]

    referrals_response = await referrer_client.get(
        f"/api/v1/workspaces/{referrer_workspace_id}/billing/referrals"
    )
    assert referrals_response.status_code == 200
    code = referrals_response.json()["code"]

    create_referred = await referred_client.post(
        "/api/v1/workspaces",
        json={"name": f"referred-ws-{unique_name}", "referral_code": code},
    )
    assert create_referred.status_code == 201
    referred_workspace_id = create_referred.json()["id"]

    row = (
        await db_session.execute(
            text(
                "SELECT referrer_workspace_id, status FROM billing_referrals "
                "WHERE referred_workspace_id = :referred"
            ),
            {"referred": referred_workspace_id},
        )
    ).one()
    assert row.referrer_workspace_id == referrer_workspace_id
    assert row.status == "pending"


async def test_an_unknown_referral_code_never_fails_workspace_creation(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    user_id = f"user-{unique_name}"
    await _make_user(db_session, user_id)
    client = make_client(user_id)

    response = await client.post(
        "/api/v1/workspaces",
        json={"name": f"ws-{unique_name}", "referral_code": "GARBAGE1"},
    )
    assert response.status_code == 201
    workspace_id = response.json()["id"]

    row = (
        await db_session.execute(
            text("SELECT count(*) FROM billing_referrals WHERE referred_workspace_id = :ws"),
            {"ws": workspace_id},
        )
    ).scalar_one()
    assert row == 0
