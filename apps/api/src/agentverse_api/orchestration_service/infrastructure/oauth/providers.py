"""The OAuth2 provider registry — the piece the Phase 6 scaffolding was
built for but never got (`docs/PHASE-6-MCP-CHECKLIST.md` gap #1).

`oauth_sessions`, the repository's `create_oauth_session`/
`consume_oauth_session`, and `OauthStartResponse` all existed already;
nothing populated an authorization URL or exchanged a code for a token.
This module supplies the one thing that was missing: where each
catalog entry's provider actually lives.

Authorize/token endpoints and scope separators are protocol facts about
each provider, not configuration — they do not vary per workspace or
per deployment, so they are a literal registry, not a settings field.
Only the credential pair (this AgentVerse deployment's own registered
OAuth app) comes from `Settings`.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_api.infrastructure.config import Settings


@dataclass(frozen=True, slots=True)
class OAuthProviderConfig:
    slug: str
    authorize_url: str
    token_url: str
    client_id: str
    client_secret: str
    #: Most providers space-join scopes; a few (historically Facebook-
    #: style APIs, and some HubSpot scope sets) use a comma. Explicit per
    #: provider rather than assumed, since a wrong separator produces a
    #: token silently scoped to fewer permissions than requested instead
    #: of an error.
    scope_separator: str = " "


#: Static protocol endpoints for every oauth2-schemed catalog entry.
#: Keyed by the catalog `slug` (`McpServer.slug`), not a free-standing
#: provider name, so `build_oauth_providers` can look one up directly
#: from the installed server's catalog entry with no second mapping.
_ENDPOINTS: dict[str, tuple[str, str]] = {
    "notion": ("https://api.notion.com/v1/oauth/authorize", "https://api.notion.com/v1/oauth/token"),
    "linear": ("https://linear.app/oauth/authorize", "https://api.linear.app/oauth/token"),
    "jira": (
        "https://auth.atlassian.com/authorize",
        "https://auth.atlassian.com/oauth/token",
    ),
    "hubspot": (
        "https://app.hubspot.com/oauth/authorize",
        "https://api.hubapi.com/oauth/v1/token",
    ),
    "cloudflare": (
        "https://dash.cloudflare.com/oauth2/authorize",
        "https://dash.cloudflare.com/oauth2/token",
    ),
}


def build_oauth_providers(settings: Settings) -> dict[str, OAuthProviderConfig]:
    """Every provider whose credential pair is actually configured.

    Mirrors `apps/web/lib/social-providers.ts`'s `enabledSocialProviders`:
    a provider missing either half of its client id/secret is absent from
    the returned mapping, not present with an empty string. `start()`
    then reports "not configured" for it exactly as it would for a slug
    it has never heard of — same failure mode, so there is nothing here
    that leaks which providers are half-registered.
    """
    pairs: dict[str, tuple[str | None, str | None]] = {
        "notion": (settings.notion_oauth_client_id, settings.notion_oauth_client_secret),
        "linear": (settings.linear_oauth_client_id, settings.linear_oauth_client_secret),
        "jira": (settings.jira_oauth_client_id, settings.jira_oauth_client_secret),
        "hubspot": (settings.hubspot_oauth_client_id, settings.hubspot_oauth_client_secret),
        "cloudflare": (
            settings.cloudflare_oauth_client_id,
            settings.cloudflare_oauth_client_secret,
        ),
    }
    providers: dict[str, OAuthProviderConfig] = {}
    for slug, (client_id, client_secret) in pairs.items():
        if not client_id or not client_secret:
            continue
        authorize_url, token_url = _ENDPOINTS[slug]
        providers[slug] = OAuthProviderConfig(
            slug=slug,
            authorize_url=authorize_url,
            token_url=token_url,
            client_id=client_id,
            client_secret=client_secret,
            scope_separator="," if slug == "hubspot" else " ",
        )
    return providers
