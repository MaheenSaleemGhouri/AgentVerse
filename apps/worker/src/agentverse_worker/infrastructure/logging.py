"""Structured JSON logging (CLAUDE.md §7 — never `print()`).

Mirrors apps/api's formatter so log aggregation treats both services'
output identically. `request_id` doesn't apply to a worker process the
same way it does an HTTP request — this context var is reserved for a
future `job_id`/`run_id` binding once Phase 3/4 land real job
execution; the formatter already emits whatever keys are bound.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)


class JSONFormatter(logging.Formatter):
    """Renders one JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        job_id = job_id_var.get()
        if job_id is not None:
            payload["job_id"] = job_id

        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    """Wire the root logger to emit structured JSON on stdout exactly once."""
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)
