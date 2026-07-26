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


@lru_cache
def get_settings() -> Settings:
    """Process-wide singleton — avoids re-parsing the environment per call."""
    return Settings()
