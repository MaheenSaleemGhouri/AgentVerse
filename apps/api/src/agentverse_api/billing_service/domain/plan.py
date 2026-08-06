"""The plan catalog: tiers, the dimensions they limit, the capabilities
they gate, and the arithmetic over them.

Pure — no I/O, no framework, no database. Every number a customer is
ever shown or charged passes through a function in this module, and
CLAUDE.md §11 requires that arithmetic be unit-testable without touching
Postgres or Stripe.

Three deliberate decisions are encoded here rather than left to callers:

**Money is integer cents, everywhere** (Rule 15). Sub-cent amounts do
exist in this system — a single LLM call routinely costs a fraction of a
cent — but they live in `agentverse_shared.cost_accounting`'s micro-USD
unit and are converted to cents exactly once, at the invoice boundary.
Nothing in this module is ever a float.

**Overage is priced per increment, not per unit.** "$2 per 1,000 agent
runs" is expressible in integer cents; "$0.002 per run" is not. Storing
the increment alongside the price is what keeps Rule 15 satisfiable for
rates that are genuinely sub-cent per unit.

**Unlimited is `None`, never a sentinel like -1 or a very large int.**
A sentinel invites `if limit > used` to quietly do the right thing for
the wrong reason, and one refactor later it does the wrong thing
silently. `None` forces every call site to say what unlimited means.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PlanTier(StrEnum):
    """The four tiers, fixed by CLAUDE.md §1's domain vocabulary.

    `TEAM` is the collaboration tier — seats, shared workspaces, SSO,
    audit logs, priority support. Its customer-facing name is the
    `display_name` column on `plans`, configurable from the backend
    without a code change, so renaming it (to "Business", say) is one
    UPDATE and never a migration.
    """

    FREE = "free"
    PRO = "pro"
    TEAM = "team"
    ENTERPRISE = "enterprise"


# Rank exists so "is this an upgrade or a downgrade?" is one comparison
# rather than a conditional tree repeated at every call site that needs
# to decide between immediate proration and end-of-period scheduling.
_TIER_RANK: dict[PlanTier, int] = {
    PlanTier.FREE: 0,
    PlanTier.PRO: 1,
    PlanTier.TEAM: 2,
    PlanTier.ENTERPRISE: 3,
}


def tier_rank(tier: PlanTier) -> int:
    return _TIER_RANK[tier]


def is_upgrade(*, current: PlanTier, target: PlanTier) -> bool:
    return _TIER_RANK[target] > _TIER_RANK[current]


def is_downgrade(*, current: PlanTier, target: PlanTier) -> bool:
    return _TIER_RANK[target] < _TIER_RANK[current]


class BillingInterval(StrEnum):
    MONTHLY = "monthly"
    ANNUAL = "annual"


class ResourceLimit(StrEnum):
    """Dimensions counted as a *standing* quantity — how many exist right
    now, not how many happened this month.

    Checked before a create, and the answer changes when something is
    deleted. Distinct from `MeteredDimension`, which only ever accrues.
    """

    AGENTS = "agents"
    TEAMS = "teams"
    KNOWLEDGE_BASES = "knowledge_bases"
    MCP_CONNECTIONS = "mcp_connections"
    SEATS = "seats"
    CONCURRENT_RUNS = "concurrent_runs"


class MeteredDimension(StrEnum):
    """Dimensions that accrue over a billing period and reset with it.

    Every member must map to a countable event the platform already
    records — `saas-strategist`'s rule that a metered dimension is never
    a fuzzy "usage unit". The mapping to its durable source is asserted
    by a test rather than left to this docstring.
    """

    AGENT_RUNS = "agent_runs"
    TOKENS = "tokens"
    MCP_CALLS = "mcp_calls"
    WORKFLOW_EXECUTIONS = "workflow_executions"
    BACKGROUND_JOBS = "background_jobs"
    API_CALLS = "api_calls"
    BANDWIDTH_MB = "bandwidth_mb"
    KNOWLEDGE_STORAGE_MB = "knowledge_storage_mb"
    VECTOR_STORAGE_MB = "vector_storage_mb"


class Capability(StrEnum):
    """Boolean feature gates, as opposed to numeric limits.

    A capability answers "may this workspace do this at all", which is
    why it is separate from `ResourceLimit`: `max agents = 0` and "agents
    are not part of your plan" are different messages to show a user.
    """

    MULTI_AGENT = "multi_agent"
    PRIORITY_QUEUE = "priority_queue"
    ANALYTICS = "analytics"
    TEAM_COLLABORATION = "team_collaboration"
    SSO = "sso"
    SCIM = "scim"
    AUDIT_LOG_EXPORT = "audit_log_export"
    CUSTOM_ROLES = "custom_roles"
    IP_ALLOWLIST = "ip_allowlist"
    COMMUNITY_SUPPORT = "community_support"
    PRIORITY_SUPPORT = "priority_support"
    DEDICATED_SUPPORT = "dedicated_support"
    DEDICATED_INFRASTRUCTURE = "dedicated_infrastructure"
    SLA = "sla"
    WHITE_LABEL = "white_label"
    CUSTOM_INTEGRATIONS = "custom_integrations"


@dataclass(frozen=True, slots=True)
class OverageRate:
    """What a workspace pays once it passes a metered dimension's
    included allowance.

    `included_allowance` duplicates nothing: the plan's *limit* on a
    metered dimension is exactly the allowance, and a dimension with an
    overage rate is one where exceeding the allowance costs money rather
    than being refused. A dimension with no `OverageRate` is a hard stop.
    """

    dimension: MeteredDimension
    billing_increment: int
    price_cents_per_increment: int

    def __post_init__(self) -> None:
        if self.billing_increment <= 0:
            raise ValueError(
                f"billing_increment must be positive for {self.dimension}, "
                f"got {self.billing_increment}"
            )
        if self.price_cents_per_increment < 0:
            raise ValueError(
                f"price_cents_per_increment must not be negative for {self.dimension}, "
                f"got {self.price_cents_per_increment}"
            )


@dataclass(frozen=True, slots=True)
class Plan:
    """A row of the catalog, as the rest of the system sees it.

    `slug` is the stable identifier every other table foreign-keys to and
    every entitlement check compares against. `display_name` is what a
    customer reads. They are separate columns so marketing can rename a
    tier without invalidating stored subscriptions.
    """

    id: str
    slug: PlanTier
    display_name: str
    description: str
    monthly_price_cents: int | None
    annual_price_cents: int | None
    currency: str
    trial_days: int
    is_public: bool
    is_active: bool
    sort_order: int
    resource_limits: dict[ResourceLimit, int | None]
    metered_allowances: dict[MeteredDimension, int | None]
    capabilities: frozenset[Capability]
    overage_rates: dict[MeteredDimension, OverageRate]
    #: Public-API requests admitted per minute. `None` is unlimited, the
    #: same convention every other quota here uses, so "not configured"
    #: never silently means zero.
    #:
    #: Lives on the plan rather than in the limiter because it is a
    #: packaging decision — `saas-pricing-expert` owns the numbers — and
    #: a second copy in code would be the one that gets edited.
    #:
    #: Defaulted, and last, so every existing construction site is
    #: unchanged.
    api_rate_limit_per_minute: int | None = None

    @property
    def is_custom_priced(self) -> bool:
        """Enterprise is quoted, not published.

        Expressed as "no published price" rather than `slug == ENTERPRISE`
        so the pricing page's "Contact sales" branch follows the actual
        data, and a future custom-priced tier does not need the UI edited.
        """
        return self.monthly_price_cents is None and self.annual_price_cents is None

    def resource_limit(self, limit: ResourceLimit) -> int | None:
        """`None` means unlimited *and* is also what an unconfigured
        dimension returns — deliberately. A plan that does not mention a
        dimension does not constrain it; the alternative (defaulting to
        zero) would silently forbid a feature the moment someone adds a
        new dimension to the enum, which is the opposite of safe.
        """
        return self.resource_limits.get(limit)

    def metered_allowance(self, dimension: MeteredDimension) -> int | None:
        return self.metered_allowances.get(dimension)

    def grants(self, capability: Capability) -> bool:
        return capability in self.capabilities


def within_resource_limit(*, limit: int | None, current: int) -> bool:
    """Can one more be created? `current` is the count *before* creating.

    Unlimited (`None`) always admits. A limit of 0 always refuses, which
    is how a tier expresses "this resource is not part of your plan" as a
    number rather than as a missing capability.
    """
    if limit is None:
        return True
    return current < limit


def remaining(*, limit: int | None, used: int) -> int | None:
    """Headroom, floored at zero. `None` stays `None`: there is no
    meaningful "remaining" on an unlimited dimension, and returning a
    large number instead would make a progress bar render a lie.
    """
    if limit is None:
        return None
    return max(0, limit - used)


def usage_percent(*, limit: int | None, used: int) -> int | None:
    """Whole-percent usage for quota bars and the 80%/100% upgrade
    nudges. `None` on unlimited, and on a zero limit — 0/0 has no
    percentage, and reporting 100% for a dimension the plan does not
    include would fire an upgrade nudge for something the upgrade does
    not fix.
    """
    if limit is None or limit == 0:
        return None
    return min(100, (used * 100) // limit)


def overage_units(*, allowance: int | None, used: int, increment: int) -> int:
    """Billable increments beyond the allowance, always rounded **up**.

    Rounding up is the industry convention and, more to the point, is the
    only choice that keeps `sum(overage of parts) >= overage of sum`
    from silently under-billing. An unlimited allowance is never in
    overage.
    """
    if increment <= 0:
        raise ValueError(f"increment must be positive, got {increment}")
    if allowance is None:
        return 0
    excess = used - allowance
    if excess <= 0:
        return 0
    return -(-excess // increment)


def overage_cents(*, allowance: int | None, used: int, rate: OverageRate) -> int:
    """Integer cents owed for exceeding `allowance` on one dimension."""
    units = overage_units(
        allowance=allowance,
        used=used,
        increment=rate.billing_increment,
    )
    return units * rate.price_cents_per_increment


def price_cents(plan: Plan, interval: BillingInterval) -> int | None:
    """`None` for a custom-priced tier — the caller must render "contact
    sales" rather than a number it invented.
    """
    if interval is BillingInterval.ANNUAL:
        return plan.annual_price_cents
    return plan.monthly_price_cents


def annual_saving_percent(plan: Plan) -> int | None:
    """How much the annual price saves against twelve monthly payments,
    as a whole percent — the number the pricing page's annual toggle
    shows.

    `None` when either price is absent (custom-priced tiers) or when the
    monthly price is zero (Free saves nothing, and 0/0 is not 0%).
    Truncated rather than rounded: claiming 17% when the real saving is
    16.6% overstates a commercial promise by a hair, and understating it
    is the safe direction.
    """
    monthly = plan.monthly_price_cents
    annual = plan.annual_price_cents
    if monthly is None or annual is None or monthly == 0:
        return None
    full_year = monthly * 12
    if annual >= full_year:
        return None
    return ((full_year - annual) * 100) // full_year
