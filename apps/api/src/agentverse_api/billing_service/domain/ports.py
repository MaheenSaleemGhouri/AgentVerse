"""Repository ports for the billing context.

`infrastructure/repositories.py` implements these against Postgres;
`tests/` implements them in memory. Application-layer use cases depend
only on what is declared here (CLAUDE.md §5).
"""

from __future__ import annotations

from typing import Protocol

from agentverse_api.billing_service.domain.entitlements import ResourceUsage
from agentverse_api.billing_service.domain.plan import Plan, PlanTier


class PlanRepository(Protocol):
    """The catalog. Read-only from the application's side: plans are
    configured through migrations and the admin path, never mutated as a
    side effect of serving a request, so no `create`/`update` appears
    here.
    """

    async def list_active(self, *, public_only: bool) -> list[Plan]:
        """Active plans in `sort_order`, then tier rank.

        `public_only` exists because the catalog legitimately holds rows
        the pricing page must not show — a grandfathered legacy plan
        still has to resolve for the workspaces on it, but publishing it
        would offer a price the product no longer sells.
        """
        ...

    async def get_by_slug(self, slug: PlanTier) -> Plan | None: ...


class WorkspaceUsageRepository(Protocol):
    """Standing resource counts for one workspace.

    Deliberately one call returning every dimension rather than a method
    per dimension: the entitlements endpoint needs all of them at once,
    and five round trips to render one panel is the N+1 this shape
    exists to prevent.

    The counts come from tables owned by other bounded contexts
    (`agents`, `teams`, `knowledge_bases`, MCP installations,
    `workspace_members`). Billing does **not** query them: each owning
    repository grew a `count_for_workspace` method, and the adapter
    behind this port composes those. Rule 5 forbids reaching into
    another context's tables, and a counting query is not an exception
    to it — a `WHERE deleted_at IS NULL` clause that the owning context
    later changes would silently start billing on a different definition
    of "an agent" than the product shows.
    """

    async def resource_usage(self, workspace_id: str) -> ResourceUsage: ...
