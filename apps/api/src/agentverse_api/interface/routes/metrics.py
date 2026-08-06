"""`/internal/metrics` — Prometheus scrape endpoint for apps/api.

The worker's own metrics route says: "If that ever changes, the metrics
module is already shared and the route is nine lines." Phase 9 is that
change. Billing runs here, not in the worker, and every billing failure
this platform has is otherwise silent — a webhook that failed processing
leaves a `received` row and no customer-visible symptom until an invoice
is wrong.

**`/internal` on the internet-routable service, and that needs saying.**
apps/api *is* reachable from the internet, unlike the worker. This path
is expected to be blocked at the ingress alongside `/internal/*`, which
already carries `/internal/auth-events`. It carries no tenant data by
construction: every label comes from a closed vocabulary and
`workspace_id` is deliberately not one of them — a cardinality decision
first, and the reason this endpoint leaking would be a much smaller
problem than a tenant-scoped one.
"""

from __future__ import annotations

# Imported for its side effect: defining the counters and materialising
# their label children, so the endpoint reports zeros rather than nothing
# before the first billing event. An absent series and a zero one look
# identical to a scraper, and the alerts below depend on telling them
# apart.
from agentverse_shared.observability import billing_metrics  # noqa: F401
from agentverse_shared.observability.metrics import CONTENT_TYPE_LATEST, render_latest
from fastapi import APIRouter, Response

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """The Prometheus text exposition format, as-is.

    Not a Pydantic response model: the payload is a documented
    third-party wire format, and wrapping it would mean re-serialising a
    format whose whole contract is being byte-exact.
    """
    return Response(content=render_latest(), media_type=CONTENT_TYPE_LATEST)
