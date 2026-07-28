"""Translates a stored team member into an SDK `Agent`.

This is the whole of AgentVerse's contribution to agent construction: the
SDK owns `Agent`, `handoff()`, tool dispatch, turn management, and
tracing, and none of that is reimplemented here. What this module does is
decide *which* SDK primitives a given seat gets — which is policy, and
policy is AgentVerse's (ADR-0009: "the SDK decides how control
transfers; AgentVerse decides who is reachable").

An agent's behavior comes from its own published version, never from the
team. The team contributes exactly three things: the shared objective
prepended to instructions, the shared-memory tools, and (for a
supervisor) the set of handoff targets.
"""

from __future__ import annotations

from typing import Any

from agents import Agent, Handoff, ModelSettings, Tool, handoff
from agents.mcp import MCPServer
from agentverse_worker.agents.builtin_tools import resolve_tools
from agentverse_worker.teams.repository import MemberRecord, TeamRecord
from agentverse_worker.teams.shared_memory import SharedMemoryStore, build_shared_memory_tools

#: Used when an agent version leaves `max_output_tokens` unset, matching
#: the single-agent path so a team run and a solo run of the same agent
#: reserve the same headroom.
DEFAULT_RESERVED_OUTPUT_TOKENS = 2048


def compose_instructions(member: MemberRecord, team: TeamRecord) -> str:
    """The team brief, then the agent's own instructions.

    Order matters and is deliberate: the agent's own published
    instructions come last so they are the most recent thing the model
    read, and so a team objective can frame the work without overriding
    what the user configured. The role line exists because a model given
    three identical-looking peers routes badly — the seat has to be
    stated, not inferred.
    """
    parts: list[str] = []
    if team.objective:
        parts.append(
            f"You are part of the AI team {team.name!r}. The team's objective:\n{team.objective}"
        )
    else:
        parts.append(f"You are part of the AI team {team.name!r}.")
    parts.append(f"Your role on this team: {member.role}.")
    parts.append(str(member.config.get("system_instructions") or ""))
    return "\n\n".join(part for part in parts if part.strip())


def build_member_agent(
    member: MemberRecord,
    *,
    team: TeamRecord,
    memory: SharedMemoryStore | None,
    handoff_targets: list[Agent] | None = None,
    mcp_servers: list[MCPServer] | None = None,
) -> Agent:
    """One SDK `Agent` for one seat.

    `handoff_targets` is passed only for a supervisor. When it is set,
    the SDK's own `handoff()` runs delegation — the model chooses, and
    the transfer is an SDK tool call, not an AgentVerse control loop.

    `mcp_servers` are already wrapped in `GovernedMcpServer` by
    `attach_integrations`; this function never receives a raw SDK server,
    which is what keeps "no tool call bypasses the boundary" structural
    rather than a rule someone has to remember here.
    """
    config = member.config
    tools: list[Tool] = list(resolve_tools(list(config.get("tools") or [])))
    if memory is not None:
        tools.extend(build_shared_memory_tools(memory, agent_id=member.agent_id))

    # Annotated with the SDK's own union: `Agent.handoffs` accepts
    # either an agent or a `Handoff`, and list invariance means a
    # narrower `list[Handoff]` does not satisfy it.
    handoffs: list[Agent[Any] | Handoff[Any, Any]] = [
        # `handoff_description` on the *target* is what the delegating
        # model reads to choose. A tool description is part of the prompt
        # (`mcp-expert`), so a vague one degrades routing exactly as much
        # as a vague system prompt — which is why the seat can override
        # the agent's own description here.
        handoff(agent=target)
        for target in (handoff_targets or [])
    ]

    return Agent(
        name=member.agent_name,
        instructions=compose_instructions(member, team),
        model=str(config["model"]),
        tools=tools,
        handoffs=handoffs,
        mcp_servers=list(mcp_servers or []),
        model_settings=ModelSettings(
            temperature=config.get("temperature"),
            max_tokens=config.get("max_output_tokens"),
        ),
    )


def build_handoff_target(
    member: MemberRecord, *, team: TeamRecord, memory: SharedMemoryStore | None
) -> Agent:
    """A worker agent as seen by a delegating supervisor.

    Identical to `build_member_agent` except that the seat's
    `handoff_description` overrides the agent's own — the supervisor is
    choosing between seats, not between agents in the abstract, and the
    same agent may warrant different descriptions on different teams.
    """
    agent = build_member_agent(member, team=team, memory=memory)
    if member.handoff_description:
        agent.handoff_description = member.handoff_description
    return agent
