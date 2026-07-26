"""Agent domain entities — plain dataclasses, zero framework/ORM
imports (CLAUDE.md §5). An agent is stored, versioned configuration:
`Agent` is identity/lifecycle metadata, `AgentVersion` is the immutable
config snapshot the builder writes and the runtime reads
(`CLAUDE.md` §4 Agents — never hand-authored outside the builder).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class AgentStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class AgentConfig:
    """The versioned, runtime-facing shape of an agent's configuration.

    `tools` names members of Phase 4's fixed, built-in demo tool set —
    proving "single-agent-with-tools" without the formal central
    tool-execution boundary, which is Phase 6's deliverable, not this
    phase's. Stored as `agent_versions.config` JSONB; this dataclass is
    the domain-typed view of it (CLAUDE.md §8: "the DB stores
    flexibility, the API enforces shape").
    """

    model: str
    system_instructions: str
    temperature: float | None = None
    max_output_tokens: int | None = None
    tools: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Agent:
    id: str
    workspace_id: str
    name: str
    description: str | None
    status: AgentStatus
    published_version_id: str | None
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AgentVersion:
    id: str
    agent_id: str
    version_number: int
    config: AgentConfig
    created_by_user_id: str
    created_at: datetime
