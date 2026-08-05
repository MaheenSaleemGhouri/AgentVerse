"""What a workspace is actually allowed to do right now: its plan's
limits set against its real counts.

Pure functions over already-fetched numbers. The counting queries live
in the infrastructure layer; nothing here touches a database, so the
rule "at 100 agents on a 100-agent plan, refuse the 101st" is testable
without one.

The split between `ResourceUsage` (what was measured) and
`EntitlementLine` (what that means) is deliberate: the same measurement
feeds the quota-enforcement dependency, the usage panel, and the upgrade
nudge, and each of those must derive its answer from one shared rule
rather than three near-identical comparisons drifting apart.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_api.billing_service.domain.plan import (
    Capability,
    MeteredDimension,
    Plan,
    ResourceLimit,
    remaining,
    usage_percent,
    within_resource_limit,
)

# The share of a quota at which the product warns rather than blocks.
# `saas-strategist` fixes the in-product nudge at 80%: early enough to
# act on, late enough that it is not noise. It lives here, once, so the
# usage panel and the notification job cannot disagree about when a
# workspace is "approaching" its limit.
NUDGE_THRESHOLD_PERCENT = 80


@dataclass(frozen=True, slots=True)
class ResourceUsage:
    """Current standing counts for one workspace.

    Every field is a real count from a real table. There is no default —
    a caller that cannot measure a dimension must say so rather than
    pass zero, because zero is indistinguishable from "measured and
    empty" and would show a customer a full quota bar's worth of
    headroom they may not have.
    """

    agents: int
    teams: int
    knowledge_bases: int
    mcp_connections: int
    seats: int

    def count_for(self, limit: ResourceLimit) -> int | None:
        """`None` for dimensions this snapshot does not measure.

        `CONCURRENT_RUNS` is the live one: it is a point-in-time property
        of the queue, not a row count, so it is enforced at run
        submission rather than reported here. Returning `None` says that
        plainly instead of reporting a zero that is not true.
        """
        match limit:
            case ResourceLimit.AGENTS:
                return self.agents
            case ResourceLimit.TEAMS:
                return self.teams
            case ResourceLimit.KNOWLEDGE_BASES:
                return self.knowledge_bases
            case ResourceLimit.MCP_CONNECTIONS:
                return self.mcp_connections
            case ResourceLimit.SEATS:
                return self.seats
            case ResourceLimit.CONCURRENT_RUNS:
                return None


@dataclass(frozen=True, slots=True)
class EntitlementLine:
    """One dimension's answer, in the shape both the API response and
    the quota check consume.

    `limit is None` means unlimited, and then `remaining` and
    `percent_used` are `None` too — a progress bar has nothing to draw,
    and the UI must render "Unlimited" rather than a full or empty track.
    """

    dimension: str
    limit: int | None
    used: int
    remaining: int | None
    percent_used: int | None
    at_limit: bool
    approaching_limit: bool


def _line(*, dimension: str, limit: int | None, used: int) -> EntitlementLine:
    percent = usage_percent(limit=limit, used=used)
    return EntitlementLine(
        dimension=dimension,
        limit=limit,
        used=used,
        remaining=remaining(limit=limit, used=used),
        percent_used=percent,
        # `at_limit` is `used >= limit`, not `> limit`: a workspace with
        # 100 of 100 agents is at its limit even though it has not
        # exceeded it, and that is the moment the create button must
        # refuse rather than one agent later.
        at_limit=limit is not None and used >= limit,
        approaching_limit=percent is not None and percent >= NUDGE_THRESHOLD_PERCENT,
    )


def resource_lines(*, plan: Plan, usage: ResourceUsage) -> list[EntitlementLine]:
    """One line per measurable standing dimension, in enum order so the
    UI's row order is stable across requests rather than dependent on
    dict iteration.

    Dimensions the snapshot cannot measure are omitted, not zero-filled.
    """
    lines: list[EntitlementLine] = []
    for limit in ResourceLimit:
        used = usage.count_for(limit)
        if used is None:
            continue
        lines.append(
            _line(
                dimension=limit.value,
                limit=plan.resource_limit(limit),
                used=used,
            )
        )
    return lines


def metered_lines(
    *, plan: Plan, period_usage: dict[MeteredDimension, int]
) -> list[EntitlementLine]:
    """One line per metered dimension for the current billing period.

    A dimension absent from `period_usage` is reported as zero, which is
    correct here and not a guess: metered usage accrues from an
    append-only event stream, so "no rows this period" genuinely is zero
    used — unlike a standing count, which can fail to be measured.
    """
    return [
        _line(
            dimension=dimension.value,
            limit=plan.metered_allowance(dimension),
            used=period_usage.get(dimension, 0),
        )
        for dimension in MeteredDimension
    ]


@dataclass(frozen=True, slots=True)
class Entitlements:
    """The complete answer for one workspace: which plan, what it allows,
    and how close the workspace is to each edge of it.
    """

    workspace_id: str
    plan: Plan
    resources: list[EntitlementLine]
    metered: list[EntitlementLine]

    @property
    def capabilities(self) -> frozenset[Capability]:
        return self.plan.capabilities

    def grants(self, capability: Capability) -> bool:
        return self.plan.grants(capability)


def can_create(*, plan: Plan, limit: ResourceLimit, current_count: int) -> bool:
    """The single rule the create-path quota check calls.

    Kept as a named function rather than inlined so that every
    "may I create one more?" in the codebase resolves to the same
    comparison — the drift this prevents is the kind that lets one
    endpoint allow a 101st agent that another endpoint refuses.
    """
    return within_resource_limit(limit=plan.resource_limit(limit), current=current_count)
