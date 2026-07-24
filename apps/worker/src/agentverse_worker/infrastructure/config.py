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


@lru_cache
def get_settings() -> Settings:
    """Process-wide singleton — avoids re-parsing the environment per call."""
    return Settings()
