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
