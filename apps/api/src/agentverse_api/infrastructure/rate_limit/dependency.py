"""Per-workspace and per-API-key rate limiting, as a dependency.

**Why a dependency rather than middleware.** §7 says "enforced at the
gateway/middleware before any expensive work begins", and this is the
reading that survives Rule 6. Middleware runs *before* authentication,
so a per-workspace limit written there could only key off the path
parameter — client-supplied `workspace_id`, which Rule 6 forbids
absolutely and which a caller could simply vary to get a fresh bucket.
Composed on `get_current_workspace` instead, the key comes from the
credential, and FastAPI still resolves it before the handler body, so
nothing expensive has run.

**Two buckets, and the smaller one wins.** A request authenticated by an
API key is counted against both the workspace and the key. The workspace
bucket is what the plan sells; the key bucket stops one leaked or
misbehaving integration from consuming the whole workspace's budget
while its neighbours starve. Both are incremented on every request —
counting only against whichever is currently tighter would let a caller
alternate credentials to stay under both.

Responses always carry the budget, not only refusals: a client that
learns its limit only by being refused cannot pace itself.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.get_current_workspace import (
    get_current_workspace,
)
from agentverse_api.billing_service.infrastructure.repositories import (
    SqlPlanRepository,
    SqlSubscriptionRepository,
)
from agentverse_api.infrastructure.config import get_settings
from agentverse_api.infrastructure.db import get_db_session
from agentverse_api.infrastructure.rate_limit.limiter import (
    RateLimiterUnavailableError,
    RateLimitScope,
    RedisRateLimiter,
)
from agentverse_api.infrastructure.rate_limit.window import RateLimitDecision
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_redis_client,
)

#: What a workspace gets before any subscription exists — a trial, a
#: half-finished signup, a plan row that has not been read yet. Equal to
#: the Free tier's published limit, so an unsubscribed workspace is
#: never accidentally more privileged than a paying one.
DEFAULT_LIMIT_PER_MINUTE = 60

#: An individual API key's ceiling, regardless of plan. Stops one leaked
#: or looping integration from spending a whole workspace's budget while
#: its siblings starve. Deliberately a constant rather than a per-key
#: column: a per-key override is a feature nobody has asked for, and
#: shipping the column now would mean shipping the UI to manage it.
API_KEY_LIMIT_PER_MINUTE = 600


def _apply_headers(response: Response, decision: RateLimitDecision) -> None:
    """Advertise the budget on every response, refused or not."""
    response.headers["RateLimit-Limit"] = str(decision.limit)
    response.headers["RateLimit-Remaining"] = str(decision.remaining)
    response.headers["RateLimit-Reset"] = str(decision.reset_at)


async def _plan_limit(session: AsyncSession, workspace_id: str) -> int | None:
    """The workspace's per-minute allowance, from its live subscription.

    Falls back to the default rather than to unlimited when there is no
    subscription: an unbilled workspace is exactly the one that should
    not get an unmetered API.
    """
    subscription = await SqlSubscriptionRepository(session).get_for_workspace(workspace_id)
    if subscription is None:
        return DEFAULT_LIMIT_PER_MINUTE
    plan = await SqlPlanRepository(session).get_by_slug(subscription.plan_slug)
    if plan is None:
        return DEFAULT_LIMIT_PER_MINUTE
    return plan.api_rate_limit_per_minute


async def enforce_rate_limit(
    response: Response,
    context: WorkspaceContext = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db_session),
) -> WorkspaceContext:
    """Refuse, or pass through the context the route was going to use.

    Returns the `WorkspaceContext` so a route can depend on this instead
    of `get_current_workspace` without resolving the workspace twice.
    """
    settings = get_settings()
    limiter = RedisRateLimiter(get_redis_client(), environment=settings.environment)

    scopes = [
        RateLimitScope(
            kind="workspace",
            identifier=context.workspace_id,
            limit=await _plan_limit(session, context.workspace_id),
        )
    ]
    if context.api_key_id is not None:
        scopes.append(
            RateLimitScope(
                kind="api_key",
                identifier=context.api_key_id,
                limit=API_KEY_LIMIT_PER_MINUTE,
            )
        )

    refused: RateLimitDecision | None = None
    tightest: RateLimitDecision | None = None
    for scope in scopes:
        try:
            decision = await limiter.check(scope)
        except RateLimiterUnavailableError as exc:
            # Fail closed (§7). 503 rather than 429 because the caller is
            # not over their budget — we cannot tell what their budget
            # is. `Retry-After` is short: this is expected to be a blip.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rate limiting is temporarily unavailable. Please retry shortly.",
                headers={"Retry-After": "5"},
            ) from exc

        # Every scope is counted even once one has refused: skipping the
        # rest would let a caller alternate credentials to keep the other
        # buckets artificially low.
        if not decision.allowed and refused is None:
            refused = decision
        if tightest is None or decision.remaining < tightest.remaining:
            tightest = decision

    if refused is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "rate_limited",
                "message": "Too many requests. Slow down and retry after the interval given.",
                "retry_after": refused.retry_after_seconds,
            },
            headers={
                "Retry-After": str(refused.retry_after_seconds),
                "RateLimit-Limit": str(refused.limit),
                "RateLimit-Remaining": "0",
                "RateLimit-Reset": str(refused.reset_at),
            },
        )

    if tightest is not None:
        _apply_headers(response, tightest)
    return context
