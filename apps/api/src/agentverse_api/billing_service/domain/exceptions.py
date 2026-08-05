"""Billing domain errors. The interface layer maps these onto the shared
error envelope; this layer never imports FastAPI to raise them directly
(CLAUDE.md §5).
"""

from __future__ import annotations

from agentverse_api.billing_service.domain.plan import PlanTier


class PlanNotFoundError(Exception):
    """No active plan with this slug in the catalog. Maps to HTTP 404.

    Reachable in normal operation, not only through a bad request: a plan
    can be deactivated while a client still holds its slug from a cached
    pricing page, and that must read as "gone" rather than as a 500.
    """

    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(f"No active plan with slug {slug!r}")


class SubscriptionNotFoundError(Exception):
    """This workspace has no live subscription. Maps to HTTP 404.

    Not an error state for the workspace itself — a Free workspace has
    never subscribed and is operating exactly as intended. It is an error
    only for callers that asked specifically for a subscription.
    """

    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id
        super().__init__(f"Workspace {workspace_id!r} has no live subscription")


class SubscriptionAlreadyExistsError(Exception):
    """The workspace already has a live subscription. Maps to HTTP 409.

    Enforced in the database too, by a partial unique index on
    non-canceled rows. Two live subscriptions would make "what plan is
    this workspace on" a coin flip and could bill the same workspace
    twice in one period.
    """

    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id
        super().__init__(f"Workspace {workspace_id!r} already has a live subscription")


class PlanNotPurchasableError(Exception):
    """The target plan cannot be subscribed to directly. Maps to HTTP 422.

    Covers the two real cases: Enterprise is quoted by sales and has no
    published price to charge, and a deactivated legacy plan still
    resolves for the workspaces grandfathered onto it but must not accept
    new ones.
    """

    def __init__(self, slug: str, detail: str) -> None:
        self.slug = slug
        self.detail = detail
        super().__init__(f"Plan {slug!r} is not directly purchasable: {detail}")


class CatalogIncompleteError(Exception):
    """The catalog is missing a tier the platform cannot run without.

    Raised at resolution time rather than swallowed with a hardcoded
    fallback. A workspace with no subscription is on Free by definition,
    so if the Free plan row is absent the correct behaviour is a loud
    failure — inventing limits in code would put the enforced quota and
    the published catalog permanently out of sync, which is exactly the
    single-source-of-truth violation this table exists to prevent
    (Rule 3).
    """

    def __init__(self, slug: PlanTier) -> None:
        self.slug = slug
        super().__init__(
            f"Plan catalog is missing the required {slug.value!r} tier; "
            "seed migration has not run or the row was deactivated"
        )
