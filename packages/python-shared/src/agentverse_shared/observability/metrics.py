"""RED/USE metrics for the tool-execution boundary and MCP integrations.

Implements the dashboard defined in
`docs/observability/tool-execution-monitoring.md`. Shared rather than
worker-local because the egress guard and the credential envelope both
live in this package and are called from both services — a metric
defined next to its call site would end up defined twice with different
names (CLAUDE.md §3, and Rule 3: one source of truth per definition).

## Cardinality is enforced here, not trusted from call sites

The monitoring design originally labelled these metrics with
`workspace_id`, `installed_server_id`, and `tool_name`. Instrumenting it
made that untenable and the design was changed rather than shipped:

- `workspace_id` is unbounded by construction — it grows with the
  customer base, and every new tenant permanently adds series to every
  metric it touches.
- `tool_name` is worse, because it is **attacker-influenced**. A custom
  MCP server declares its own tool names, so a server advertising ten
  thousand tools would mint ten thousand label values. That turns our
  own monitoring into the denial-of-service target.

None of that attribution is lost: it lives in `tool_calls`, which is
partitioned, workspace-scoped, and already exposed through
`GET /integrations/metrics`. Prometheus gets the bounded operational
signals — is the fleet healthy, is anything being refused — and the
per-tenant question is answered by the tenant-scoped API that was built
for it.

So every label value passes through `_bounded()`. A caller that passes
something unexpected produces `other`, never a new series. That makes
the ceiling on cardinality a property of this module rather than a
convention call sites are trusted to follow.

## Process model

Metrics are per-process, held in the default registry, and exposed by
each container's own `/internal/metrics`. This is correct as long as one
container runs one process: the worker's consumer loop runs inside the
ASGI app, so it is started with a single uvicorn worker. Running it with
`--workers N` would silently scrape one process out of N and undercount
everything by roughly that factor — noted because the failure is quiet.
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

__all__ = [
    "CONTENT_TYPE_LATEST",
    "DENIAL_REASONS",
    "EGRESS_RANGES",
    "MCP_CONNECT_OUTCOMES",
    "TOOL_STATUSES",
    "record_breaker_opened",
    "record_credential_unseal_failure",
    "record_egress_denial",
    "record_mcp_connect",
    "record_tool_call",
    "render_latest",
]

# --- Bounded label vocabularies -------------------------------------
#
# Every one of these is a closed set defined in code. Adding a value is
# a deliberate edit here, which is the point: it makes "we added a label
# value" a reviewable change rather than a runtime surprise.

#: Terminal states of a governed tool call. Mirrors `tool_calls.status`.
TOOL_STATUSES = frozenset({"success", "cached", "denied", "circuit_open", "timeout", "error"})

#: *Which control* refused a call — not the human-readable reason, which
#: embeds tool names and is therefore unbounded. The reason text stays in
#: `tool_calls.denial_reason` where it is useful and costs nothing.
DENIAL_REASONS = frozenset(
    {"circuit_open", "permission", "invalid_arguments", "budget_exceeded", "egress"}
)

#: Why the egress guard rejected a destination. `metadata` is broken out
#: from `link_local` even though 169.254.169.254 is inside 169.254.0.0/16:
#: a call to the cloud metadata address is a credential-theft attempt,
#: and a call to some other link-local address is usually a
#: misconfiguration. Merging them would bury the first in the second.
EGRESS_RANGES = frozenset(
    {
        "metadata",
        "link_local",
        "loopback",
        "rfc1918",
        "cgnat",
        "multicast",
        "reserved",
        "documentation",
        "not_global",
        "unresolvable",
        "scheme",
        "url_credentials",
        "redirect_chain",
    }
)

#: Result of attaching one MCP server at run start.
MCP_CONNECT_OUTCOMES = frozenset({"healthy", "degraded", "unreachable"})

#: What any unrecognised label value collapses to.
OTHER = "other"


def _bounded(value: str, allowed: frozenset[str]) -> str:
    """Clamps a label value to a known vocabulary.

    The whole cardinality guarantee of this module rests on this
    function, so it is deliberately total: it cannot raise, because a
    metric that throws would turn an observability gap into an outage on
    a path that includes every tool call.
    """
    return value if value in allowed else OTHER


# --- Metrics ---------------------------------------------------------

TOOL_CALLS = Counter(
    "agentverse_tool_calls_total",
    "Governed tool calls by terminal status. Refusals are included and "
    "are not errors — see the monitoring doc on why they are separated.",
    ["status"],
)

TOOL_CALL_DURATION = Histogram(
    "agentverse_tool_call_duration_seconds",
    "End-to-end duration of a governed tool call, including the third "
    "party. Third-party-dominated: informational, not an SLO.",
    # Topped out at the boundary's own MAX_TIMEOUT_SECONDS — a bucket
    # above the hard cutoff could never be filled.
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)

TOOL_BOUNDARY_OVERHEAD = Histogram(
    "agentverse_tool_boundary_overhead_seconds",
    "Time the boundary itself spent (breaker, permission, validation, "
    "budget, cache, sanitise), excluding the external call. This is the "
    "number that is our defect when it breaches.",
    buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
)

TOOL_DENIALS = Counter(
    "agentverse_tool_calls_denied_total",
    "Tool calls stopped by a control, labelled with which control stopped it.",
    ["reason"],
)

EGRESS_DENIALS = Counter(
    "agentverse_egress_denied_total",
    "Outbound destinations rejected by the egress guard. Expected to be "
    "flat zero; a single increment on `metadata` is a paging event.",
    ["range"],
)

MCP_CONNECTS = Counter(
    "agentverse_mcp_connect_total",
    "MCP server attachment attempts at run start, by outcome.",
    ["outcome"],
)

MCP_CONNECT_DURATION = Histogram(
    "agentverse_mcp_connect_duration_seconds",
    "Time to connect to an MCP server and discover its tools.",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

BREAKER_OPENED = Counter(
    "agentverse_circuit_breaker_opened_total",
    "Circuit breaker open transitions. A counter rather than a per-server "
    "gauge because `installed_server_id` is unbounded; which server is "
    "open is answered by the workspace-scoped integrations API.",
)

CREDENTIAL_UNSEAL_FAILURES = Counter(
    "agentverse_credential_unseal_failures_total",
    "Failures decrypting a stored MCP credential. Steady state is zero: "
    "a non-zero value means a KEK mismatch between services or an AAD "
    "mismatch, and the latter means a row was moved between workspaces.",
)


# --- Recording -------------------------------------------------------
#
# Thin free functions rather than exported metric objects, so call sites
# cannot pass a label this module has not vetted, and so the signature
# documents what each metric expects.


def record_tool_call(
    *,
    status: str,
    duration_seconds: float,
    overhead_seconds: float,
    denial_reason: str | None = None,
) -> None:
    """Records one completed pass through the boundary.

    `overhead_seconds` is our time, `duration_seconds` is everything.
    Both are recorded on every call including refusals — a refusal that
    became slow is exactly the regression the budget doc cares about,
    since refusals are the path an attacker exercises repeatedly.
    """
    TOOL_CALLS.labels(status=_bounded(status, TOOL_STATUSES)).inc()
    TOOL_CALL_DURATION.observe(max(0.0, duration_seconds))
    TOOL_BOUNDARY_OVERHEAD.observe(max(0.0, overhead_seconds))
    if denial_reason is not None:
        TOOL_DENIALS.labels(reason=_bounded(denial_reason, DENIAL_REASONS)).inc()


def record_egress_denial(range_name: str) -> None:
    EGRESS_DENIALS.labels(range=_bounded(range_name, EGRESS_RANGES)).inc()


def record_mcp_connect(*, outcome: str, duration_seconds: float) -> None:
    MCP_CONNECTS.labels(outcome=_bounded(outcome, MCP_CONNECT_OUTCOMES)).inc()
    MCP_CONNECT_DURATION.observe(max(0.0, duration_seconds))


def record_breaker_opened() -> None:
    BREAKER_OPENED.inc()


def record_credential_unseal_failure() -> None:
    CREDENTIAL_UNSEAL_FAILURES.inc()


def render_latest() -> bytes:
    """The exposition payload for `/internal/metrics`."""
    return generate_latest()


def _initialise_label_children() -> None:
    """Materialises every label child at zero on import.

    `prometheus_client` creates a child series the first time
    `.labels(...)` is called, so a counter that has never fired exposes
    no samples at all — only a HELP line. For an alert like
    `increase(agentverse_egress_denied_total[5m]) > 0` that is the
    difference between "no denials, all is well" and "this process is not
    reporting", and the two must not look identical on the one metric
    whose whole purpose is to be zero until something is badly wrong.

    Bounded by construction: these are the same closed vocabularies
    declared above, so this adds a fixed number of series per process,
    not a growing one.
    """
    for status in TOOL_STATUSES:
        TOOL_CALLS.labels(status=status)
    for reason in DENIAL_REASONS:
        TOOL_DENIALS.labels(reason=reason)
    for range_name in EGRESS_RANGES:
        EGRESS_DENIALS.labels(range=range_name)
    for outcome in MCP_CONNECT_OUTCOMES:
        MCP_CONNECTS.labels(outcome=outcome)


_initialise_label_children()
