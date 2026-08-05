"""Typed application configuration, loaded once (CLAUDE.md §7).

No `os.environ` reads happen anywhere else in this codebase — every
setting is declared here so a missing required value fails startup
loudly instead of surfacing as a runtime `KeyError` deep in a request.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENTVERSE_API_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    service_name: str = "agentverse-api"
    environment: Literal["development", "staging", "production", "test"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    host: str = "0.0.0.0"  # noqa: S104 - container-internal bind address, not internet-exposed directly
    port: int = 8000

    # Required, no default: Postgres is this service's system of record
    # (CLAUDE.md §8) — a missing value fails startup loudly rather than
    # surfacing as a runtime connection error on the first request.
    database_url: str

    # Two distinct URLs for Better Auth (ADR-0005) — deliberately NOT one
    # setting, because they answer different questions and are genuinely
    # different values under Docker Compose:
    #
    # - auth_internal_url: where apps/api reaches apps/web server-to-server
    #   to fetch the JWKS document (e.g. "http://web:3000", the Docker
    #   network hostname).
    # - auth_public_url: the browser-facing origin Better Auth was
    #   configured with (its own `baseURL`) — this is what actually ends
    #   up in every JWT's `iss`/`aud` claims (e.g. "http://localhost:3000").
    #
    # Collapsing these into one value would make JWKS fetches fail in
    # dev (apps/api's "localhost" is its own container, not apps/web's)
    # or make issuer/audience validation fail (a container-internal
    # hostname the browser never used to authenticate would never match
    # the claims Better Auth actually signed).
    auth_internal_url: str
    auth_public_url: str

    # Required, no default: shared secret validating server-to-server calls
    # from apps/web's Better Auth hooks (e.g. /internal/auth-events) — zero
    # trust means the internal network boundary alone is not sufficient
    # authorization (CLAUDE.md §10).
    internal_api_secret: str

    @property
    def auth_jwks_url(self) -> str:
        return f"{self.auth_internal_url}/api/auth/jwks"

    # Required, no default (CLAUDE.md Rule 1: a missing secret fails
    # startup loudly). The only place this key is read — every adapter
    # call goes through `orchestration_service.infrastructure.providers
    # .openai_adapter`, never a route or workflow reading it directly.
    openai_api_key: str
    # Override for a self-hosted/compatible endpoint or a test double;
    # `None` means the SDK's own default (https://api.openai.com/v1).
    openai_base_url: str | None = None

    # Phase 3: producer side of apps/worker's Redis Streams queue. The
    # two services share only this wire contract (stream key + field
    # schema, documented in docs/systems/queue-dlq-policy.md) — never
    # code, per CLAUDE.md's service-boundary rule.
    redis_url: str = "redis://localhost:6379/0"
    queue_stream: str = "queue:jobs"

    # Phase 5 — knowledge bases. The storage root must be outside any
    # web-served directory; nothing serves these files over HTTP
    # (CLAUDE.md §10). apps/worker reads the same root under its own
    # setting — same value, separately declared, because the two services
    # share the key layout as a contract, never a config object.
    document_storage_root: str = "/var/lib/agentverse/documents"

    # Caps the blast radius of one upload — embedding spend, worker
    # memory, and request-body buffering all scale with it. 25 MB fits a
    # large PDF manual without letting a single request pin a worker.
    max_document_bytes: int = 25 * 1024 * 1024

    # New knowledge bases are created with this embedding identity.
    # Existing ones keep whatever they were created with, so retrieval
    # never mixes versions mid-backfill.
    embedding_model: str = "text-embedding-3-small"
    embedding_model_version: str = "1"

    # Phase 6 gap-closure — OAuth2 completion. This service's own
    # browser-reachable origin: the redirect_uri registered with every
    # OAuth provider below points here, never at auth_internal_url (that
    # is apps/web's server-to-server hostname, which the user's browser
    # cannot reach). Required, no default, for the same reason
    # auth_public_url is: a wrong value fails a redirect, not a request.
    api_public_url: str

    # Per-provider OAuth2 app credentials, one pair per catalog entry
    # whose auth_scheme is oauth2 (Notion, Linear, Jira, HubSpot,
    # Cloudflare). Each is optional and independent — deliberately not a
    # single "oauth configured" flag — because a workspace should be able
    # to use whichever of these AgentVerse has actually registered an
    # app with, exactly the pattern apps/web already uses for GitHub/
    # Google (`lib/social-providers.ts`): a provider without both halves
    # of its pair is absent from `build_oauth_providers`, not a button
    # that fails on click.
    notion_oauth_client_id: str | None = None
    notion_oauth_client_secret: str | None = None
    linear_oauth_client_id: str | None = None
    linear_oauth_client_secret: str | None = None
    jira_oauth_client_id: str | None = None
    jira_oauth_client_secret: str | None = None
    hubspot_oauth_client_id: str | None = None
    hubspot_oauth_client_secret: str | None = None
    cloudflare_oauth_client_id: str | None = None
    cloudflare_oauth_client_secret: str | None = None

    # Phase 9 — Stripe. Optional as a pair, deliberately: local
    # development, CI, and preview environments legitimately run with no
    # payment provider, and the routes that need one answer 503 rather
    # than 500-ing on a `None`. Same shape as the OAuth pairs above — a
    # provider without credentials is absent, not a button that fails on
    # click.
    #
    # These are secrets (Rule 1): they live in the environment or the
    # secrets manager, never in source, and are never logged. There is no
    # `os.environ.get(..., "sk_test_changeme")` fallback anywhere — a
    # placeholder default would let a misconfigured production process
    # start and silently take no money.
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None

    # Pinned, never "latest": Stripe changes response shapes between API
    # versions, and inheriting whatever the account's default happens to
    # be makes this service's behaviour depend on a dashboard setting
    # nobody in this repo can see or review.
    stripe_api_version: str = "2025-10-29.clover"

    @property
    def stripe_configured(self) -> bool:
        """Both halves, or neither. A secret key without a webhook secret
        would take payments this service could never learn the outcome
        of — worse than not being configured at all.
        """
        return bool(self.stripe_secret_key and self.stripe_webhook_secret)

    @property
    def stripe_is_live_mode(self) -> bool:
        return bool(self.stripe_secret_key and self.stripe_secret_key.startswith("sk_live_"))

    def validate_stripe_mode(self) -> None:
        """Refuse a key whose mode contradicts the environment.

        Both directions are real incidents rather than hypotheticals. A
        test key in production means customers complete checkout and are
        never charged, while the product behaves as though they were. A
        live key outside production means a developer running the test
        suite, or a preview environment handling a stray webhook, can
        move real money.

        Called at startup so the process dies loudly rather than
        discovering this on the first checkout.
        """
        if not self.stripe_secret_key:
            return
        if self.environment == "production" and not self.stripe_is_live_mode:
            raise ValueError(
                "Refusing to start: AGENTVERSE_API_STRIPE_SECRET_KEY is not a live-mode "
                "key (expected the sk_live_ prefix) but the environment is production. "
                "Customers would complete checkout without ever being charged."
            )
        if self.environment != "production" and self.stripe_is_live_mode:
            raise ValueError(
                f"Refusing to start: a live-mode Stripe key is configured in the "
                f"{self.environment!r} environment. This process could move real money."
            )


@lru_cache
def get_settings() -> Settings:
    """Process-wide singleton — avoids re-parsing the environment per call."""
    return Settings()
