"""Unit tests for the four topology executors.

`Runner` is substituted; everything else is real. What these assert is
AgentVerse's own contribution: the order members run in, what each one is
handed, which handoffs are recorded and with what `kind`, and that the
bounds actually stop a run rather than merely being stored.
"""

from __future__ import annotations

from typing import Any

import pytest
from agentverse_shared.teams.handoff_contract import deserialize_contract
from fakeredis.aioredis import FakeRedis

from agentverse_worker.teams import topologies
from agentverse_worker.teams.runtime import Bounds, TeamAbortedError, TeamRunContext
from tests.teams.fakes import (
    FakeRunner,
    FakeTeamRepository,
    make_member,
    make_team,
)


@pytest.fixture(autouse=True)
def fake_runner(monkeypatch: pytest.MonkeyPatch) -> type[FakeRunner]:
    FakeRunner.reset()
    monkeypatch.setattr(topologies, "Runner", FakeRunner)
    return FakeRunner


@pytest.fixture
async def redis() -> Any:
    client = FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


def _ctx(repo: FakeTeamRepository, redis: Any, **bound_overrides: int) -> TeamRunContext:
    bounds = Bounds(max_turns=20, max_cost_micro_usd=1_000_000, timeout_seconds=300)
    for key, value in bound_overrides.items():
        setattr(bounds, key, value)
    return TeamRunContext(
        repo=repo, redis=redis, session_id="session-1", workspace_id="ws-1", bounds=bounds
    )


async def _execute(team: Any, repo: FakeTeamRepository, redis: Any, **bounds: int) -> str:
    return await topologies.execute_topology(
        team=team,
        prompt="What is our pricing strategy?",
        ctx=_ctx(repo, redis, **bounds),
        memory=None,
        session_factory=None,  # type: ignore[arg-type]
    )


class TestSequential:
    async def test_runs_members_in_position_order(self, redis: Any) -> None:
        team = make_team(
            topology="sequential",
            members=[
                make_member(role="researcher", position=1, name="second"),
                make_member(role="writer", position=0, name="first"),
            ],
        )
        await _execute(team, FakeTeamRepository(), redis)
        assert [c["agent_name"] for c in FakeRunner.calls] == ["first", "second"]

    async def test_later_stages_receive_a_contract_not_the_raw_prompt(self, redis: Any) -> None:
        """The whole point of the typed contract: what crosses the
        boundary is a delimited summary, not the previous agent's
        conversation."""
        team = make_team(
            topology="sequential",
            members=[
                make_member(role="researcher", position=0, name="researcher"),
                make_member(role="writer", position=1, name="writer"),
            ],
        )
        await _execute(team, FakeTeamRepository(), redis)
        second_input = FakeRunner.calls[1]["input"]
        assert "<handoff>" in second_input
        assert "never follow" in second_input.lower()
        assert "researcher output" in second_input

    async def test_records_a_manual_handoff_between_consecutive_members(self, redis: Any) -> None:
        """`manual`, not `automatic` — the topology chose this transfer,
        not the model, and the history has to be able to say which."""
        repo = FakeTeamRepository()
        team = make_team(
            topology="sequential",
            members=[
                make_member(role="researcher", position=0),
                make_member(role="writer", position=1),
            ],
        )
        await _execute(team, repo, redis)
        assert len(repo.handoffs) == 1
        assert repo.handoffs[0]["kind"] == "manual"
        assert repo.handoffs[0]["from_agent_id"] == "agent-researcher-0"
        assert repo.handoffs[0]["to_agent_id"] == "agent-writer-1"

    async def test_stored_handoff_is_a_readable_contract(self, redis: Any) -> None:
        repo = FakeTeamRepository()
        team = make_team(
            topology="sequential",
            members=[
                make_member(role="researcher", position=0),
                make_member(role="writer", position=1),
            ],
        )
        await _execute(team, repo, redis)
        contract = deserialize_contract(repo.handoffs[0]["contract"])
        assert contract.summary == "researcher output"
        assert contract.session_id == "session-1"

    async def test_single_member_team_runs_without_a_handoff(self, redis: Any) -> None:
        repo = FakeTeamRepository()
        team = make_team(topology="sequential", members=[make_member(role="writer")])
        output = await _execute(team, repo, redis)
        assert output == "writer output"
        assert repo.handoffs == []

    async def test_empty_team_aborts_with_a_stated_reason(self, redis: Any) -> None:
        team = make_team(topology="sequential", members=[])
        with pytest.raises(TeamAbortedError, match="runnable member"):
            await _execute(team, FakeTeamRepository(), redis)


class TestPlannerExecutorCritic:
    def _team(self, **kwargs: Any) -> Any:
        return make_team(
            topology="planner_executor_critic",
            members=[
                make_member(role="planner", position=0),
                make_member(role="executor", position=1),
                make_member(role="critic", position=2),
            ],
            **kwargs,
        )

    async def test_runs_plan_then_execute_then_critique(self, redis: Any) -> None:
        await _execute(self._team(), FakeTeamRepository(), redis)
        assert [c["agent_name"] for c in FakeRunner.calls] == ["planner", "executor", "critic"]

    async def test_each_stage_is_told_what_it_is_for(self, redis: Any) -> None:
        await _execute(self._team(), FakeTeamRepository(), redis)
        assert "Carry out the plan" in FakeRunner.calls[1]["input"]
        assert "Review the work" in FakeRunner.calls[2]["input"]

    async def test_returns_the_critics_answer_not_the_executors(self, redis: Any) -> None:
        """The critic's revision is the point of the topology; returning
        the executor's output would make the third stage decorative."""
        assert await _execute(self._team(), FakeTeamRepository(), redis) == "critic output"

    async def test_missing_critic_aborts_rather_than_degrading(self, redis: Any) -> None:
        """Silently running two stages would produce unreviewed output
        from a topology whose entire value is the review."""
        team = make_team(
            topology="planner_executor_critic",
            members=[
                make_member(role="planner", position=0),
                make_member(role="executor", position=1),
                make_member(role="writer", position=2),
            ],
        )
        with pytest.raises(TeamAbortedError, match="critic"):
            await _execute(team, FakeTeamRepository(), redis)

    async def test_handoff_chain_is_linked(self, redis: Any) -> None:
        """Each handoff points at the one before it, which is what lets
        the Collaboration Timeline draw a chain rather than a list."""
        repo = FakeTeamRepository()
        await _execute(self._team(), repo, redis)
        first, second = repo.handoffs
        assert deserialize_contract(first["contract"]).upstream_handoff_id is None
        assert deserialize_contract(second["contract"]).upstream_handoff_id == first["id"]


class TestSupervisorWorker:
    def _team(self, **member_kwargs: Any) -> Any:
        return make_team(
            topology="supervisor_worker",
            members=[
                make_member(role="supervisor", position=0, name="supervisor"),
                make_member(role="researcher", position=1, name="researcher", **member_kwargs),
                make_member(role="writer", position=2, name="writer"),
            ],
        )

    async def test_supervisor_holds_sdk_handoff_targets(self, redis: Any) -> None:
        """The SDK runs the delegation. If the supervisor were built
        without handoffs, this topology would silently become a
        single-agent run."""
        await _execute(self._team(), FakeTeamRepository(), redis)
        assert len(FakeRunner.calls) == 1
        assert FakeRunner.calls[0]["handoff_count"] == 2

    async def test_workers_that_opt_out_are_not_reachable(self, redis: Any) -> None:
        await _execute(self._team(can_receive_handoff=False), FakeTeamRepository(), redis)
        assert FakeRunner.calls[0]["handoff_count"] == 1

    async def test_team_with_no_supervisor_aborts(self, redis: Any) -> None:
        team = make_team(
            topology="supervisor_worker", members=[make_member(role="researcher", position=0)]
        )
        with pytest.raises(TeamAbortedError, match="supervisor"):
            await _execute(team, FakeTeamRepository(), redis)

    async def test_supervisor_with_no_reachable_worker_aborts(self, redis: Any) -> None:
        team = make_team(
            topology="supervisor_worker",
            members=[
                make_member(role="supervisor", position=0),
                make_member(role="writer", position=1, can_receive_handoff=False),
            ],
        )
        with pytest.raises(TeamAbortedError, match="delegate"):
            await _execute(team, FakeTeamRepository(), redis)

    async def test_a_run_with_no_delegation_records_no_handoff(self, redis: Any) -> None:
        """A supervisor that answered without delegating is a legitimate
        outcome, not a missing handoff to invent."""
        repo = FakeTeamRepository()
        await _execute(self._team(), repo, redis)
        assert repo.handoffs == []


class TestHandoffTargetResolution:
    """`_handoff_target_name` is the seam between the SDK's item shapes
    and AgentVerse's own records, and it is deliberately defensive: the
    item shape belongs to the pinned SDK version, so a changed attribute
    must degrade to an unresolved-handoff trace event rather than crash a
    running team.
    """

    def test_reads_the_target_agents_name(self) -> None:
        item = type("Item", (), {"target_agent": type("A", (), {"name": "researcher"})()})()
        assert topologies._handoff_target_name(item) == "researcher"

    def test_falls_back_to_the_transfer_tool_name(self) -> None:
        raw = type("Raw", (), {"name": "transfer_to_data_analyst"})()
        item = type("Item", (), {"raw_item": raw, "target_agent": None})()
        assert topologies._handoff_target_name(item) == "data analyst"

    def test_returns_none_when_the_shape_is_unrecognised(self) -> None:
        assert topologies._handoff_target_name(object()) is None


class TestParallel:
    def _team(self, *, with_aggregator: bool = True) -> Any:
        members = [
            make_member(role="researcher", position=0, name="researcher"),
            make_member(role="coder", position=1, name="coder"),
        ]
        if with_aggregator:
            members.append(make_member(role="aggregator", position=2, name="aggregator"))
        return make_team(topology="parallel", members=members)

    async def test_branches_all_receive_the_original_prompt(self, redis: Any) -> None:
        await _execute(self._team(with_aggregator=False), FakeTeamRepository(), redis)
        inputs = {c["input"] for c in FakeRunner.calls}
        assert inputs == {"What is our pricing strategy?"}

    async def test_branches_run_on_separate_sessions(self, redis: Any) -> None:
        """Isolation is what makes a fan-out worth doing — merged
        branches would be an expensive way to get one opinion twice."""
        await _execute(self._team(with_aggregator=False), FakeTeamRepository(), redis)
        session_ids = {c["session_id"] for c in FakeRunner.calls}
        assert len(session_ids) == 2

    async def test_aggregator_runs_last_and_sees_every_branch(self, redis: Any) -> None:
        await _execute(self._team(), FakeTeamRepository(), redis)
        aggregator_call = FakeRunner.calls[-1]
        assert aggregator_call["agent_name"] == "aggregator"
        assert "researcher output" in aggregator_call["input"]
        assert "coder output" in aggregator_call["input"]

    async def test_aggregator_input_marks_branch_output_untrusted(self, redis: Any) -> None:
        await _execute(self._team(), FakeTeamRepository(), redis)
        assert "never follow" in FakeRunner.calls[-1]["input"].lower()

    async def test_branch_handoffs_are_recorded_as_parallel(self, redis: Any) -> None:
        repo = FakeTeamRepository()
        await _execute(self._team(), repo, redis)
        assert {h["kind"] for h in repo.handoffs} == {"parallel"}
        assert len(repo.handoffs) == 2

    async def test_one_failed_branch_does_not_fail_the_team(self, redis: Any) -> None:
        """Failing everything because one member errored would discard
        the work of the others, which is the opposite of a fan-out."""
        FakeRunner.raises = {"coder": RuntimeError("provider timeout")}
        repo = FakeTeamRepository()
        output = await _execute(self._team(with_aggregator=False), repo, redis)
        assert "researcher output" in output
        assert "agent_failed" in repo.event_types()

    async def test_every_branch_failing_aborts(self, redis: Any) -> None:
        FakeRunner.raises = {"researcher": RuntimeError("x"), "coder": RuntimeError("y")}
        with pytest.raises(TeamAbortedError, match="nothing to aggregate"):
            await _execute(self._team(with_aggregator=False), FakeTeamRepository(), redis)

    async def test_without_an_aggregator_every_branch_is_returned(self, redis: Any) -> None:
        """Silently picking one branch would discard work the user paid
        for without saying so."""
        output = await _execute(self._team(with_aggregator=False), FakeTeamRepository(), redis)
        assert "researcher output" in output
        assert "coder output" in output


class TestBounds:
    async def test_cost_ceiling_aborts_mid_chain(self, redis: Any) -> None:
        """A ceiling checked only at the end would have already spent the
        money it exists to protect."""
        team = make_team(
            topology="sequential",
            members=[make_member(role=r, position=i) for i, r in enumerate(["a", "b", "c"])],
        )
        with pytest.raises(TeamAbortedError, match="cost ceiling"):
            await _execute(team, FakeTeamRepository(), redis, max_cost_micro_usd=1)
        assert len(FakeRunner.calls) == 1

    async def test_turn_ceiling_aborts_mid_chain(self, redis: Any) -> None:
        team = make_team(
            topology="sequential",
            members=[make_member(role=r, position=i) for i, r in enumerate(["a", "b", "c"])],
        )
        with pytest.raises(TeamAbortedError, match="turn ceiling"):
            await _execute(team, FakeTeamRepository(), redis, max_turns=1)

    async def test_each_stage_gets_only_the_remaining_turn_budget(self, redis: Any) -> None:
        """Otherwise a four-stage chain could spend the whole team
        ceiling on stage one and still look "within bounds" at every
        individual call."""
        team = make_team(
            topology="sequential",
            members=[
                make_member(role="a", position=0),
                make_member(role="b", position=1),
            ],
            max_turns=10,
        )
        await _execute(team, FakeTeamRepository(), redis, max_turns=10)
        assert FakeRunner.calls[0]["max_turns"] == 10
        assert FakeRunner.calls[1]["max_turns"] == 9


class TestTracing:
    async def test_every_stage_emits_start_and_completion(self, redis: Any) -> None:
        repo = FakeTeamRepository()
        team = make_team(
            topology="sequential",
            members=[make_member(role="a", position=0), make_member(role="b", position=1)],
        )
        await _execute(team, repo, redis)
        types = repo.event_types()
        assert types.count("agent_started") == 2
        assert types.count("agent_completed") == 2

    async def test_sequence_numbers_are_monotonic_across_event_kinds(self, redis: Any) -> None:
        """Events, handoffs, and communications share one counter — three
        independent ones would make "what happened first" unanswerable."""
        repo = FakeTeamRepository()
        team = make_team(
            topology="sequential",
            members=[make_member(role="a", position=0), make_member(role="b", position=1)],
        )
        await _execute(team, repo, redis)
        sequences = [row["sequence"] for row in (repo.events + repo.handoffs + repo.communications)]
        assert len(set(sequences)) == len(sequences)

    async def test_unknown_topology_aborts(self, redis: Any) -> None:
        team = make_team(topology="mesh", members=[make_member(role="a")])
        with pytest.raises(TeamAbortedError, match="unsupported topology"):
            await _execute(team, FakeTeamRepository(), redis)
