"""`/internal/metrics` — Prometheus scrape endpoint.

Internal-only for the same reason `/internal/queue/metrics` is: this
service is not internet-routable at all (CLAUDE.md §5), so the network
boundary is the control rather than a second auth layer bolted on here.

It carries no tenant data by construction — every metric in
`agentverse_shared.observability.metrics` is labelled from a closed
vocabulary, and `workspace_id` is deliberately not one of them. That is
a cardinality decision first, but it is also why this endpoint being
reachable is a much smaller problem than a tenant-scoped one would be.

Exposed from the worker only, because every event these metrics count
happens here: tool calls, egress validation for agent-initiated calls,
MCP attachment, and credential *unsealing*. apps/api seals credentials
and never opens them, so it has nothing to report — and it is the
internet-routable service, so adding a scrape surface there would be
exposure bought for no signal. If that ever changes, the metrics module
is already shared and the route is nine lines.
"""

from __future__ import annotations

from agentverse_shared.observability.metrics import CONTENT_TYPE_LATEST, render_latest
from fastapi import APIRouter, Response

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """The Prometheus text exposition format, as-is.

    Not a Pydantic response model: the payload is a documented
    third-party wire format, and wrapping it in one would mean
    re-serialising a format whose whole contract is being byte-exact.
    """
    return Response(content=render_latest(), media_type=CONTENT_TYPE_LATEST)
