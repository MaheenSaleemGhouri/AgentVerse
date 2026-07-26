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

    # CLAUDE.md Rule 17: every reasoning loop needs step, cost, AND time
    # bounds — the SDK's own `max_turns` gives the step bound; the other
    # two are AgentVerse-specific (a generic SDK has no notion of our
    # pricing or our latency budget), so they're enforced in
    # jobs/agent_run_job.py, not delegated to the SDK. Documented
    # starting defaults, not asserted production-tuned values.
    run_max_turns: int = 10
    run_timeout_seconds: float = 120.0
    run_cost_ceiling_micro_usd: int = 2_000_000  # $2.00


@lru_cache
def get_settings() -> Settings:
    """Process-wide singleton — avoids re-parsing the environment per call."""
    return Settings()
