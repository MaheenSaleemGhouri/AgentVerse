"""Agent-run domain entities — plain dataclasses, zero framework/ORM
imports (CLAUDE.md §5). `RunStatus` mirrors the canonical run lifecycle
FSM (`CLAUDE.md` §15: idle -> queued -> running -> success/error/
cancelled; "idle" is a client-side pre-submission state, never
persisted). `AgentRunStep` is step-level trace granularity (run
started, one LLM call, one tool call, run completed/failed) — not
per-token; individual streaming deltas are transient, broadcast only
over Phase 3's `run:{run_id}:events` pub/sub channel, never persisted
one row per token.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


class RunStepType(StrEnum):
    RUN_STARTED = "run_started"
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


@dataclass(frozen=True, slots=True)
class AgentRun:
    id: str
    workspace_id: str
    agent_id: str
    agent_version_id: str
    status: RunStatus
    input: dict[str, Any]
    idempotency_key: str | None
    cost_micro_usd: int | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AgentRunStep:
    id: str
    run_id: str
    workspace_id: str
    step_type: RunStepType
    sequence: int
    payload: dict[str, Any]
    cost_micro_usd: int | None
    created_at: datetime
