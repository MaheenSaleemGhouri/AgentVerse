"""`require_capability` (docs/adr/0018) — a routing decision, not a
security gate, so it must never raise: a real grant resolves `True`, a
plain non-grant resolves `False`, and — the behavior that actually
matters here — an entitlement-lookup failure (a broken DB session, in
this test) also resolves `False` rather than propagating, so a billing
lookup hiccup degrades a run's queue priority instead of blocking the
run outright.
"""

from __future__ import annotations

from typing import Any

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.interface.dependencies.require_capability import (
    require_capability,
)
from agentverse_api.billing_service.domain.plan import Capability

_CONTEXT = WorkspaceContext(workspace_id="ws-1", user_id="user-1", role=Role.MEMBER)


class _RaisingSession:
    """Stands in for `AsyncSession` — every call a repository makes
    against it fails, simulating a real DB/connection-pool hiccup rather
    than a code bug in the entitlement path itself.
    """

    async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("connection pool exhausted")


async def test_a_lookup_failure_resolves_to_not_entitled_rather_than_raising() -> None:
    dependency = require_capability(Capability.PRIORITY_QUEUE)

    result = await dependency(context=_CONTEXT, session=_RaisingSession())

    assert result is False
