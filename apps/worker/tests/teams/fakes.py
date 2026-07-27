"""Shared fakes for the team-runtime unit tests.

The LLM is replaced, never called (CLAUDE.md §11). What is under test
here is AgentVerse's own logic — topology sequencing, bounds, what gets
recorded, what crosses a handoff — none of which needs a real model, and
all of which would become slow and non-deterministic if it used one.

`FakeRunner` stands in for `Runner`, the one SDK surface these tests
must not reach. Everything else — `Agent`, `handoff()`, the session
protocol — is real.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from agentverse_worker.teams.repository import (
    MemberRecord,
    TeamRecord,
    TeamSessionRecord,
)


def make_member(
    *,
    role: str,
    position: int = 0,
    agent_id: str | None = None,
    name: str | None = None,
    model: str = "gpt-4o-mini",
    can_receive_handoff: bool = True,
    handoff_description: str | None = None,
) -> MemberRecord:
    resolved_id = agent_id or f"agent-{role}-{position}"
    return MemberRecord(
        member_id=f"member-{resolved_id}",
        agent_id=resolved_id,
        agent_name=name or role,
        role=role,
        position=position,
        handoff_description=handoff_description,
        can_receive_handoff=can_receive_handoff,
        agent_version_id=f"version-{resolved_id}",
        config={"model": model, "system_instructions": f"You are the {role}.", "tools": []},
    )


def make_team(
    *,
    topology: str,
    members: list[MemberRecord],
    max_turns: int = 20,
    max_cost_micro_usd: int = 1_000_000,
    timeout_seconds: int = 300,
    shared_memory_enabled: bool = True,
) -> TeamRecord:
    return TeamRecord(
        id="team-1",
        workspace_id="ws-1",
        name="Test Team",
        topology=topology,
        objective="Answer the question well.",
        max_turns=max_turns,
        max_cost_micro_usd=max_cost_micro_usd,
        timeout_seconds=timeout_seconds,
        shared_memory_enabled=shared_memory_enabled,
        members=members,
    )


@dataclass
class _Usage:
    input_tokens: int = 100
    output_tokens: int = 50
    requests: int = 1


@dataclass
class _ContextWrapper:
    usage: _Usage = field(default_factory=_Usage)


@dataclass
class FakeRunResult:
    """The subset of `RunResult` the runtime actually reads.

    Deliberately not a real `RunResult`: constructing one requires the
    SDK's full internal run state, and a test that had to build that
    would be testing the SDK rather than AgentVerse.
    """

    final_output: Any = "stage output"
    new_items: list[Any] = field(default_factory=list)
    context_wrapper: _ContextWrapper = field(default_factory=_ContextWrapper)


class FakeRunner:
    """Records every call so tests can assert on ordering and inputs.

    `run` is a classmethod because that is how the executors call it —
    matching the real shape means the substitution proves the call site
    works, not just that a mock was invoked.
    """

    calls: list[dict[str, Any]] = []
    results: list[FakeRunResult] = []
    raises: dict[str, Exception] = {}

    @classmethod
    def reset(cls) -> None:
        cls.calls = []
        cls.results = []
        cls.raises = {}

    @classmethod
    async def run(
        cls, agent: Any, stage_input: str, *, max_turns: int = 10, session: Any = None
    ) -> FakeRunResult:
        # A real `Runner` awaits network I/O constantly, so it yields to
        # the event loop many times per call. Without a checkpoint here
        # the fake would run to completion synchronously and
        # `asyncio.timeout` could never fire — the wall-clock ceiling
        # would look broken when it is only the fake that is unfaithful.
        await asyncio.sleep(0)
        cls.calls.append(
            {
                "agent_name": agent.name,
                "instructions": agent.instructions,
                "input": stage_input,
                "max_turns": max_turns,
                "session_id": getattr(session, "session_id", None),
                "handoff_count": len(agent.handoffs),
                "tool_names": [getattr(t, "name", "?") for t in agent.tools],
            }
        )
        if agent.name in cls.raises:
            raise cls.raises[agent.name]
        if cls.results:
            return cls.results.pop(0)
        return FakeRunResult(final_output=f"{agent.name} output")


class FakeTeamRepository:
    """In-memory `TeamRepositoryProtocol`.

    Keeps everything it was asked to write so tests can assert on the
    durable record — which, for a multi-agent run, *is* the feature: a
    handoff nobody can see afterwards did not usefully happen.
    """

    def __init__(
        self, *, session: TeamSessionRecord | None = None, team: TeamRecord | None = None
    ) -> None:
        self.session = session
        self.team = team
        self.status_updates: list[dict[str, Any]] = []
        self.handoffs: list[dict[str, Any]] = []
        self.communications: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []

    async def get_session(self, session_id: str) -> TeamSessionRecord | None:
        if self.session and self.session.id == session_id:
            return self.session
        return None

    async def get_team(self, team_id: str, *, workspace_id: str) -> TeamRecord | None:
        if self.team and self.team.id == team_id and self.team.workspace_id == workspace_id:
            return self.team
        return None

    async def update_session_status(self, **kwargs: Any) -> None:
        self.status_updates.append(kwargs)
        if self.session is not None and "status" in kwargs:
            object.__setattr__(self.session, "status", kwargs["status"])

    async def record_handoff(self, **kwargs: Any) -> str:
        handoff_id = f"handoff-{len(self.handoffs)}"
        self.handoffs.append({**kwargs, "id": handoff_id})
        return handoff_id

    async def record_communication(self, **kwargs: Any) -> None:
        self.communications.append(kwargs)

    async def record_event(self, **kwargs: Any) -> None:
        self.events.append(kwargs)

    def event_types(self) -> list[str]:
        return [event["event_type"] for event in self.events]
