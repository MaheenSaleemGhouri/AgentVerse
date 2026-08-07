"""`GET /api/v1/workspaces/{workspace_id}/search` — one query, every kind.

**This endpoint deliberately breaks the house list-response convention**
(`{"data", "next_cursor", "has_more"}` from CLAUDE.md §7), and the reason
is worth stating rather than leaving a reviewer to wonder.

That envelope exists for collections a client walks: run history, trace
events, audit logs. This is a typeahead. Nobody pages a ⌘K palette — they
type another character, which is a *new* query, and a cursor issued
against the previous one is meaningless. Results are capped per kind
instead, and `has_more` says only "narrow your search", not "fetch page
two". Bolting cursors onto it would be a contract nobody could
meaningfully call.

`workspace_id` comes from the authenticated context, never the path
(Rule 6) — the path segment is there for readability and for
`require_viewer` to resolve against, and a mismatch 404s before this
handler runs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import require_viewer
from agentverse_api.search_service.application.search_service import SearchService
from agentverse_api.search_service.domain.kinds import (
    DEFAULT_LIMIT_PER_KIND,
    MAX_LIMIT_PER_KIND,
    SearchKind,
)
from agentverse_api.search_service.interface.dependencies.services import get_search_service
from agentverse_api.search_service.interface.schemas.search import SearchResultsOut

router = APIRouter(prefix="/api/v1/workspaces", tags=["search"])


@router.get("/{workspace_id}/search", response_model=SearchResultsOut)
async def search_workspace(
    q: str = Query(
        default="",
        max_length=512,
        description=(
            "What the user typed. Terms are prefix-matched, so partial "
            "words find whole ones. A query too short to be useful "
            "returns empty groups rather than an error."
        ),
    ),
    kinds: list[SearchKind] | None = Query(
        default=None,
        description="Restrict to these kinds. Omit to search all of them.",
    ),
    limit: int = Query(
        default=DEFAULT_LIMIT_PER_KIND,
        ge=1,
        le=MAX_LIMIT_PER_KIND,
        description="Maximum hits per kind, not in total.",
    ),
    context: WorkspaceContext = Depends(require_viewer),
    service: SearchService = Depends(get_search_service),
) -> SearchResultsOut:
    """Search agents, knowledge bases, teams and the public catalog.

    `viewer` is the right floor: everything reachable here is already
    readable by a viewer through its own list endpoint. Search is a
    faster route to those rows, never a wider one — a hit it returns is
    always a page the caller could already open.

    A 512-character cap is generous on purpose. Anything longer is a
    paste, and the shared normalizer truncates to its own limit and
    searches the first terms rather than rejecting the request.
    """
    results = await service.search(
        workspace_id=context.workspace_id,
        query=q,
        kinds=kinds,
        limit_per_kind=limit,
    )
    return SearchResultsOut.from_domain(results)
