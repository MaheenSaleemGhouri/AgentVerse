"""The run context every topology executor shares: bounds, trace
recording, and handoff/communication logging.

Bounds are the reason this exists as a shared object rather than as
per-topology bookkeeping. CLAUDE.md Rule 17 requires step, cost, *and*
time ceilings on every reasoning loop, and a topology that tracked them
independently would drift — a parallel fan-out that forgot to sum its
branches' cost is a runaway bill with no error.

The division of labour with the SDK, restated because it governs every
choice in this file: the SDK owns turn management (`max_turns` on
`Runner`), tool dispatch, handoff mechanics, and tracing. AgentVerse
owns cost, wall-clock, who is reachable, and what is durably recorded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agentverse_shared.cost_accounting import TokenUsage, calculate_cost_micro_usd
from agentverse_shared.teams.handoff_contract import (
    HANDOFF_CONTRACT_SCHEMA_VERSION,
    MAX_SUMMARY_CHARS,
    HandoffContract,
)
from redis.asyncio import Redis

from agents import RunResult
from agentverse_worker.teams.events import publish_team_event
from agentverse_worker.teams.repository import MemberRecord, TeamRecord, TeamRepositoryProtocol

logger = logging.getLogger(__name__)


class TeamAbortedError(Exception):
    """A bound was exceeded, or the team cannot run as configured.

    Caught by the job handler and turned into an `error` session with a
    stated reason — never retried. Exceeding a budget is an expected
    outcome that a retry would simply repeat at double the cost.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(slots=True)
class Bounds:
    """All three ceilings, together, because any one alone is
    insufficient: a loop under the turn limit can still be a cost
    incident, and one under both can still hang on wall-clock.
    """

    max_turns: int
    max_cost_micro_usd: int
    timeout_seconds: int


class TeamRunContext:
    """Threaded through every executor. Owns the monotonic sequence
    counter, so trace events, handoffs, and communication entries share
    one ordering — three independent counters would make "what happened
    first" unanswerable from the stored rows.
    """

    def __init__(
        self,
        *,
        repo: TeamRepositoryProtocol,
        redis: Redis,
        session_id: str,
        workspace_id: str,
        bounds: Bounds,
    ) -> None:
        self._repo = repo
        self._redis = redis
        self.session_id = session_id
        self.workspace_id = workspace_id
        self.bounds = bounds
        self._sequence = 0
        self._turns = 0
        self._cost_micro_usd = 0

    @property
    def total_turns(self) -> int:
        return self._turns

    @property
    def total_cost_micro_usd(self) -> int:
        return self._cost_micro_usd

    def next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def remaining_turns(self) -> int:
        """What is left of the team's turn budget.

        Passed to the SDK's own `Runner` turn limit rather than counted
        by hand, so a multi-stage topology cannot spend the whole budget
        on its first stage.
        """
        return max(0, self.bounds.max_turns - self._turns)

    async def emit(
        self,
        event_type: str,
        *,
        agent_id: str | None = None,
        payload: dict[str, Any] | None = None,
        cost_micro_usd: int | None = None,
    ) -> None:
        """Persists a trace event and publishes the identical shape live.

        Same discipline as the single-agent path: a live subscriber and a
        client backfilling from `execution_events` after a reconnect see
        one representation of what happened, not two that can drift.
        """
        sequence = self.next_sequence()
        body = payload or {}
        await self._repo.record_event(
            session_id=self.session_id,
            workspace_id=self.workspace_id,
            event_type=event_type,
            agent_id=agent_id,
            sequence=sequence,
            payload=body,
            cost_micro_usd=cost_micro_usd,
        )
        await publish_team_event(
            self._redis,
            self.session_id,
            {
                "type": event_type,
                "sequence": sequence,
                "agent_id": agent_id,
                "payload": body,
                "cost_micro_usd": cost_micro_usd,
            },
        )

    async def log_communication(
        self,
        *,
        kind: str,
        from_agent_id: str | None,
        to_agent_id: str | None,
        content: dict[str, Any],
    ) -> None:
        await self._repo.record_communication(
            session_id=self.session_id,
            workspace_id=self.workspace_id,
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            kind=kind,
            content=content,
            sequence=self.next_sequence(),
        )

    async def record_handoff(
        self,
        *,
        contract: HandoffContract,
        kind: str,
        reason: str | None = None,
    ) -> str:
        """Writes the handoff row and emits the matching trace event.

        Both, always, and from one place: a handoff that is recorded but
        not traced is invisible in the Collaboration Timeline, and one
        traced but not recorded disappears from the handoff-history API.
        """
        handoff_id = await self._repo.record_handoff(
            session_id=self.session_id,
            workspace_id=self.workspace_id,
            from_agent_id=contract.from_agent_id,
            to_agent_id=contract.to_agent_id,
            kind=kind,
            contract=contract.to_dict(),
            reason=reason,
            sequence=self.next_sequence(),
        )
        await self.emit(
            "handoff",
            agent_id=contract.to_agent_id,
            payload={
                "handoff_id": handoff_id,
                "kind": kind,
                "from_agent_id": contract.from_agent_id,
                "to_agent_id": contract.to_agent_id,
                "summary": contract.summary,
                "next_task": contract.next_task,
                "reason": reason,
            },
        )
        await self.log_communication(
            kind="task_request",
            from_agent_id=contract.from_agent_id,
            to_agent_id=contract.to_agent_id,
            content={"handoff_id": handoff_id, "task": contract.next_task},
        )
        return handoff_id

    def account_for(self, result: RunResult, *, model: str) -> int:
        """Adds one `Runner` result to the running totals and returns its
        cost.

        Turn accounting reads the SDK's own item count rather than
        assuming one turn per `Runner` call: a single supervisor call may
        internally take many turns, and undercounting them would let a
        team quietly exceed its declared ceiling.
        """
        usage = result.context_wrapper.usage
        cost = calculate_cost_micro_usd(
            model,
            TokenUsage(prompt_tokens=usage.input_tokens, completion_tokens=usage.output_tokens),
        )
        self._cost_micro_usd += cost
        self._turns += max(1, usage.requests)
        return cost

    def enforce_bounds(self) -> None:
        """Checked after every stage, not only at the end — a topology
        that only checked at completion would have already spent the
        money it was supposed to be protecting.
        """
        if self._cost_micro_usd > self.bounds.max_cost_micro_usd:
            raise TeamAbortedError(
                f"exceeded team cost ceiling of {self.bounds.max_cost_micro_usd} micro-USD "
                f"(spent {self._cost_micro_usd})"
            )
        if self._turns >= self.bounds.max_turns:
            raise TeamAbortedError(f"exceeded team turn ceiling of {self.bounds.max_turns} turns")


def final_text(result: RunResult) -> str:
    """The stage's output as text.

    `final_output` is typed `Any` by the SDK because an agent may declare
    a structured output type. Coerced here rather than at each call site
    so one topology cannot start passing a non-string into a contract
    that promises `str`.
    """
    output = result.final_output
    return output if isinstance(output, str) else str(output)


def contract_from_result(
    result: RunResult,
    *,
    session_id: str,
    sender: MemberRecord | None,
    receiver: MemberRecord,
    next_task: str | None,
    upstream_handoff_id: str | None = None,
) -> HandoffContract:
    """Builds the typed payload that crosses to the next member.

    The summary is the sending stage's output, truncated to the
    contract's own cap. Truncation rather than rejection because a
    verbose stage is normal model behavior, and failing a whole team
    session over it would make the bound a liability rather than a
    protection — while passing it through uncapped is the cost
    compounding the contract exists to prevent.
    """
    summary = final_text(result).strip() or "(no output)"
    if len(summary) > MAX_SUMMARY_CHARS:
        summary = summary[: MAX_SUMMARY_CHARS - 3].rstrip() + "..."
    return HandoffContract(
        schema_version=HANDOFF_CONTRACT_SCHEMA_VERSION,
        summary=summary,
        session_id=session_id,
        from_agent_id=sender.agent_id if sender else None,
        to_agent_id=receiver.agent_id,
        next_task=next_task,
        upstream_handoff_id=upstream_handoff_id,
    )


def require_members(team: TeamRecord, *, minimum: int = 1) -> list[MemberRecord]:
    members = team.ordered_members()
    if len(members) < minimum:
        raise TeamAbortedError(
            f"team {team.name!r} has {len(members)} runnable member(s) but its "
            f"{team.topology} topology needs at least {minimum}. A member whose agent "
            "has no published version is not runnable."
        )
    return members
