"""Typed application configuration, loaded once (CLAUDE.md §7)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENTVERSE_WORKER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    service_name: str = "agentverse-worker"
    environment: Literal["development", "staging", "production", "test"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    host: str = "0.0.0.0"  # noqa: S104 - container-internal bind address, not internet-exposed directly
    port: int = 8001

    redis_url: str = "redis://localhost:6379/0"
    queue_stream: str = "queue:jobs"
    queue_dlq_stream: str = "queue:jobs.dlq"
    queue_group: str = "workers"
    queue_visibility_timeout_ms: int = 30_000
    queue_base_delay_seconds: float = 0.5
    queue_max_delay_seconds: float = 8.0
    queue_block_ms: int = 5_000
    queue_batch_size: int = 10

    # Phase 4: same Postgres instance apps/api owns the schema of — this
    # service reads agent_versions and reads/writes agent_runs/
    # agent_run_steps as the orchestration_service's execution tier, not
    # as a separate bounded context with its own schema (CLAUDE.md §5's
    # "no service accesses another service's database" targets genuinely
    # independent contexts; a worker fleet executing its owning
    # service's background jobs against the same schema is the
    # accepted, common exception — same reasoning as any API+worker
    # split over one database).
    database_url: str

    # Required, no default (CLAUDE.md Rule 1): the Agents SDK call in
    # jobs/agent_run_job.py is the only place this key is read.
    openai_api_key: str
    openai_base_url: str | None = None

    # Phase 11 — Anthropic as a second model provider on the real
    # agent-run path, resolved by `agents.model_resolution.resolve_model`
    # into an `agents.extensions.models.litellm_model.LitellmModel`.
    # Optional, mirroring apps/api's Settings of the same name: a
    # deployment simply doesn't offer Anthropic-prefixed models until
    # this is set.
    anthropic_api_key: str | None = None

    @property
    def anthropic_configured(self) -> bool:
        return self.anthropic_api_key is not None

    def validate_anthropic(self) -> None:
        """No half-state to guard today — see apps/api's identical method
        for the full rationale this mirrors."""
        return

    # CLAUDE.md Rule 17: every reasoning loop needs step, cost, AND time
    # bounds — the SDK's own `max_turns` gives the step bound; the other
    # two are AgentVerse-specific (a generic SDK has no notion of our
    # pricing or our latency budget), so they're enforced in
    # jobs/agent_run_job.py, not delegated to the SDK. Documented
    # starting defaults, not asserted production-tuned values.
    run_max_turns: int = 10
    run_timeout_seconds: float = 120.0
    run_cost_ceiling_micro_usd: int = 2_000_000  # $2.00

    # Phase 5 (knowledge bases). These must agree with each knowledge
    # base's stored `embedding_model`/`embedding_model_version`; the
    # ingestion job refuses to run when they diverge rather than writing
    # vectors that cannot be compared with the ones already indexed.
    embedding_model: str = "text-embedding-3-small"
    embedding_model_version: str = "1"

    # Where uploaded knowledge-base documents live. Must be outside any
    # web-served directory (CLAUDE.md §10) and must be the *same*
    # location apps/api writes uploads to — the API writes, this worker
    # reads. In Docker that is a shared volume.
    document_storage_root: str = "/var/lib/agentverse/documents"

    # S3-compatible object storage (Neon Object Storage in production) —
    # mirrors apps/api's settings of the same name exactly, since both
    # services must resolve to the same store (this worker reads what
    # apps/api wrote). See apps/api's config.py for the full rationale.
    document_storage_bucket: str | None = None
    document_storage_endpoint_url: str | None = None
    document_storage_region: str | None = None
    document_storage_access_key_id: str | None = None
    document_storage_secret_access_key: str | None = None

    @property
    def document_storage_configured(self) -> bool:
        """All four S3 settings, or none — mirrors apps/api's Settings."""
        return bool(
            self.document_storage_bucket
            and self.document_storage_endpoint_url
            and self.document_storage_region
            and self.document_storage_access_key_id
            and self.document_storage_secret_access_key
        )

    def validate_document_storage(self) -> None:
        fields = (
            self.document_storage_bucket,
            self.document_storage_endpoint_url,
            self.document_storage_region,
            self.document_storage_access_key_id,
            self.document_storage_secret_access_key,
        )
        if any(fields) and not self.document_storage_configured:
            raise ValueError(
                "Refusing to start: AGENTVERSE_WORKER_DOCUMENT_STORAGE_* is partially "
                "configured. Set bucket, endpoint_url, region, access_key_id, and "
                "secret_access_key together, or leave all five unset to fall back "
                "to LocalDocumentStore."
            )

    # Phase 6 gap-closure — scheduled MCP health sweep (previously
    # on-demand only via `check_health`, which nothing called). A whole
    # sweep cycle, not a per-server cadence: simpler to reason about, and
    # 38 catalog entries plus custom registrations is nowhere near enough
    # volume for one sweep to threaten the interval.
    mcp_health_sweep_interval_seconds: float = 300.0
    #: Bounds how many servers this replica probes at once — a handful
    #: of slow/unreachable servers must not serialize behind each other
    #: and stretch one sweep into the next.
    mcp_health_sweep_concurrency: int = 5
    #: Per-server cap, independent of whatever timeout the SDK's own
    #: transport applies internally (CLAUDE.md Rule 17: every loop needs
    #: its own explicit bound, not just a hoped-for one from a dependency).
    mcp_health_sweep_check_timeout_seconds: float = 20.0

    # Phase 6 gap-closure — `tool_metrics` rollup (previously an unused
    # table with no writer). Every 15 minutes re-aggregates the last two
    # complete hourly buckets; the trailing window is self-healing, not
    # a cadence claim, so this can run far less often than an hour and
    # still stay correct.
    tool_metrics_aggregation_interval_seconds: float = 900.0

    # Retention enforcement — deletes run history older than each
    # workspace's configured `workspace_settings.retention_days`. Hourly
    # rather than continuous: retention is a policy measured in days, so
    # a purge running within an hour of the boundary is exactly as
    # correct and far cheaper.
    retention_sweep_interval_seconds: float = 3600.0
    #: Rows deleted per statement, per workspace, per cycle. Bounded so a
    #: workspace that just lowered its retention from 365 to 7 days does
    #: not issue one enormous DELETE that holds locks on `agent_runs`
    #: (`postgresql-expert`); the remainder is picked up next cycle.
    retention_sweep_batch_size: int = 1000

    #: How often the webhook queue is drained. Seconds, not hours: unlike
    #: retention this is latency a customer feels — a webhook that
    #: arrives an hour after the run it describes is not a webhook.
    webhook_drain_interval_seconds: float = 5.0
    #: Deliveries attempted per cycle, per replica. Each one is a network
    #: round trip to a third party with a ten-second ceiling, so the
    #: batch bounds how long a cycle can take when every endpoint is
    #: timing out.
    webhook_drain_batch_size: int = 25


@lru_cache
def get_settings() -> Settings:
    """Process-wide singleton — avoids re-parsing the environment per call."""
    return Settings()
