"""RED metrics for the billing surface.

Separate module from `metrics.py` because the two are emitted by
different services — the tool-execution metrics come from the worker,
these come from apps/api — and keeping them apart makes "which process
should be exposing this?" answerable by import path. They share the
default registry and the same `/internal/metrics` exposition, so nothing
about scraping changes.

**The same cardinality discipline applies, and for a sharper reason
here.** `workspace_id` is unbounded by construction, and billing metrics
are exactly the ones a growing customer base would multiply. None of the
per-tenant attribution is lost: it lives in `subscription_events`,
`billing_usage_events` and `billing_webhook_events`, all workspace-scoped
and queryable. Prometheus gets the bounded operational question — is
billing healthy — and the per-customer question is answered by the
tables built for it.

**What these exist to catch.** Every one of them is a failure that is
otherwise silent:

- A webhook that fails processing leaves a `received` row and no
  customer-visible symptom until an invoice is wrong.
- A quota refusal is a correct 429, but a *spike* of them is a plan
  mispriced or a limit set wrong.
- Credit-balance drift means the projection disagrees with its ledger,
  which nothing else surfaces.
- An email that never left is invisible by definition.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

__all__ = [
    "CREDIT_DRIFT_DETECTED",
    "NOTIFICATION_DELIVERY_OUTCOMES",
    "PROVIDER_OPERATIONS",
    "QUOTA_DIMENSIONS",
    "WEBHOOK_OUTCOMES",
    "record_credit_drift",
    "record_notification_delivery",
    "record_provider_call",
    "record_quota_refusal",
    "record_webhook",
]

#: Terminal states of a provider webhook. Mirrors `WebhookOutcome`.
WEBHOOK_OUTCOMES: frozenset[str] = frozenset(
    {"processed", "duplicate", "ignored", "failed"}
)

#: Metered dimensions a request can be refused on. Mirrors
#: `MeteredDimension`, and is a closed set for the same reason: it is
#: defined in code, so adding one is a reviewable edit rather than a
#: runtime surprise.
QUOTA_DIMENSIONS: frozenset[str] = frozenset(
    {
        "agent_runs",
        "tokens",
        "mcp_calls",
        "workflow_executions",
        "background_jobs",
        "api_calls",
        "bandwidth_mb",
        "knowledge_storage_mb",
        "vector_storage_mb",
    }
)

#: Payment-provider operations worth timing separately. Deliberately
#: coarse — the question these answer is "is the provider slow or
#: erroring", not "which of forty SDK methods was called".
PROVIDER_OPERATIONS: frozenset[str] = frozenset(
    {"checkout", "portal", "subscription", "invoice", "payment_method", "refund"}
)

NOTIFICATION_DELIVERY_OUTCOMES: frozenset[str] = frozenset({"sent", "failed", "skipped"})


def _bounded(value: str, allowed: frozenset[str]) -> str:
    """Anything unexpected becomes `other`, never a new series.

    Same guard as `metrics._bounded`: it makes the cardinality ceiling a
    property of this module rather than a convention call sites are
    trusted to follow.
    """
    return value if value in allowed else "other"


WEBHOOKS = Counter(
    "agentverse_billing_webhooks_total",
    "Payment-provider webhooks received, by processing outcome.",
    labelnames=("outcome",),
)

WEBHOOK_DURATION = Histogram(
    "agentverse_billing_webhook_duration_seconds",
    "Time to verify and process one provider webhook.",
    # Buckets chosen against the provider's own timeout: a webhook that
    # takes longer than a few seconds gets retried, which compounds load
    # during exactly the incident that caused the slowness.
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

QUOTA_REFUSALS = Counter(
    "agentverse_quota_refusals_total",
    "Requests refused because a workspace reached a hard metered limit.",
    labelnames=("dimension",),
)

PROVIDER_CALLS = Counter(
    "agentverse_payment_provider_calls_total",
    "Calls to the payment provider, by operation and outcome.",
    labelnames=("operation", "outcome"),
)

PROVIDER_CALL_DURATION = Histogram(
    "agentverse_payment_provider_duration_seconds",
    "Payment-provider call latency.",
    labelnames=("operation",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

CREDIT_DRIFT_DETECTED = Counter(
    "agentverse_billing_credit_drift_total",
    (
        "Reconciliation runs that found a credit balance disagreeing with "
        "its own ledger. Steady state is zero."
    ),
)

NOTIFICATION_DELIVERIES = Counter(
    "agentverse_notification_deliveries_total",
    "Transactional email dispatches, by outcome.",
    labelnames=("outcome",),
)


def record_webhook(*, outcome: str, duration_seconds: float) -> None:
    WEBHOOKS.labels(outcome=_bounded(outcome, WEBHOOK_OUTCOMES)).inc()
    WEBHOOK_DURATION.observe(max(0.0, duration_seconds))


def record_quota_refusal(dimension: str) -> None:
    QUOTA_REFUSALS.labels(dimension=_bounded(dimension, QUOTA_DIMENSIONS)).inc()


def record_provider_call(
    *, operation: str, outcome: str, duration_seconds: float
) -> None:
    bounded_operation = _bounded(operation, PROVIDER_OPERATIONS)
    PROVIDER_CALLS.labels(
        operation=bounded_operation,
        outcome=outcome if outcome in ("success", "error") else "other",
    ).inc()
    PROVIDER_CALL_DURATION.labels(operation=bounded_operation).observe(
        max(0.0, duration_seconds)
    )


def record_credit_drift() -> None:
    CREDIT_DRIFT_DETECTED.inc()


def record_notification_delivery(outcome: str) -> None:
    NOTIFICATION_DELIVERIES.labels(
        outcome=_bounded(outcome, NOTIFICATION_DELIVERY_OUTCOMES)
    ).inc()


def _initialise_label_children() -> None:
    """Materialise every label child at zero on import.

    `prometheus_client` creates a child series the first time
    `.labels(...)` is called, so a counter that has never fired exposes
    no samples at all. For an alert like
    `increase(agentverse_billing_credit_drift_total[1h]) > 0`, that is
    the difference between "no drift, all is well" and "this process is
    not reporting" — and the two must not look identical on the metrics
    whose entire purpose is to be zero until something is badly wrong.
    """
    for outcome in WEBHOOK_OUTCOMES:
        WEBHOOKS.labels(outcome=outcome)
    for dimension in QUOTA_DIMENSIONS:
        QUOTA_REFUSALS.labels(dimension=dimension)
    for operation in PROVIDER_OPERATIONS:
        for outcome in ("success", "error"):
            PROVIDER_CALLS.labels(operation=operation, outcome=outcome)
        PROVIDER_CALL_DURATION.labels(operation=operation)
    for outcome in NOTIFICATION_DELIVERY_OUTCOMES:
        NOTIFICATION_DELIVERIES.labels(outcome=outcome)
    # Unlabelled counters need an explicit touch for the same reason.
    CREDIT_DRIFT_DETECTED.inc(0)


_initialise_label_children()
