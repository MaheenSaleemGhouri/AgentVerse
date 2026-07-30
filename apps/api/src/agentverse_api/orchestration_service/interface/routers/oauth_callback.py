"""`/api/v1/integrations/oauth/callback` — the OAuth2 redirect target.

Deliberately **not** nested under `/workspaces/{workspace_id}/...` like
every other integrations route. The provider redirects the user's
browser here with no workspace context of its own — it only ever echoes
back the `state` it was given — so this route cannot require the usual
`WorkspaceContext` dependency; there is nothing to resolve one from yet.
`IntegrationRepository.consume_oauth_session`'s own docstring says the
same thing about the row this route consumes.

Security here rests on `state` (unguessable, single-use, short-lived)
and PKCE, not on a bearer token — the same trust model every public
OAuth callback endpoint uses, because the browser making this request
is not authenticated to AgentVerse at all at this point in the flow.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from agentverse_api.infrastructure.config import Settings, get_settings
from agentverse_api.orchestration_service.application.oauth_flow import (
    OAuthFlowError,
    OAuthFlowService,
)
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_oauth_flow_service,
)

router = APIRouter(prefix="/api/v1/integrations/oauth", tags=["integrations"])


@router.get("/callback", response_model=None)
async def oauth_callback_route(
    state: str,
    code: str | None = None,
    error: str | None = None,
    oauth: OAuthFlowService = Depends(get_oauth_flow_service),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Exchanges the code and redirects back into the product.

    Every outcome — success, a provider-side denial, or an exchange
    failure — ends in a redirect to a page a human is looking at, never
    a bare JSON error: the party making this request is a browser
    following a 302, not an API client that would parse one.
    """
    # `/dashboard` (no workspace segment) is the one integrations-adjacent
    # route this callback can always reach: until `handle_callback`
    # succeeds, the workspace is only known inside the (possibly invalid
    # or already-consumed) `state` — there is no workspace-scoped page to
    # send an error to yet.
    error_redirect = f"{settings.auth_public_url}/dashboard?oauth=error"

    if error is not None or code is None:
        return RedirectResponse(error_redirect)

    try:
        _workspace_id, installed_server_id = await oauth.handle_callback(state=state, code=code)
    except OAuthFlowError:
        return RedirectResponse(error_redirect)

    return RedirectResponse(
        f"{settings.auth_public_url}/dashboard/{_workspace_id}/integrations/"
        f"{installed_server_id}?oauth=success"
    )
