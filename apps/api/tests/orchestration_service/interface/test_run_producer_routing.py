"""`get_run_producer`'s stream-selection decision (docs/adr/0018) — pure
given the boolean `require_capability` already resolved, so this is
tested directly against that boolean rather than through a real
entitlement lookup (which `tests/billing_service/application/
test_entitlement_service.py` already covers for `EntitlementService.
grants` itself, and `require_capability`'s own fail-open behavior is
covered where it's declared).
"""

from __future__ import annotations

from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_run_producer,
)


async def test_entitled_workspace_routes_onto_the_priority_stream() -> None:
    producer = await get_run_producer(entitled=True)

    assert producer._stream == "queue:jobs.priority"  # noqa: SLF001 - asserting the routing decision


async def test_unentitled_workspace_routes_onto_the_default_stream() -> None:
    producer = await get_run_producer(entitled=False)

    assert producer._stream == "queue:jobs"  # noqa: SLF001 - asserting the routing decision
