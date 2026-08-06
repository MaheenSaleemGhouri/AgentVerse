"""`/internal/metrics` on apps/api serves the billing surface.

The worker's own suite checks that no alert rule names a metric nothing
emits, resolving the billing families from their declaring module rather
than from its endpoint — because the worker does not produce them.

This is the other half: the assertion that apps/api's endpoint actually
serves those families. Without it, "no rule names a metric nothing
emits" would rest on a module declaring a counter that no process ever
exposes, which is exactly the silent-alert failure the cross-check
exists to prevent.
"""

from __future__ import annotations

import re
from pathlib import Path

from httpx import AsyncClient

_OBSERVABILITY = Path(__file__).resolve().parents[4] / "infra" / "observability"
ALERTS_FILE = _OBSERVABILITY / "alerts.yml"


async def test_metrics_endpoint_serves_the_exposition_format(client: AsyncClient) -> None:
    response = await client.get("/internal/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")


async def test_billing_series_exist_from_process_start(client: AsyncClient) -> None:
    """The series exist before their first billing event, not only after.

    Three of the billing alerts are `increase(...) > 0` against metrics
    whose steady state is zero. A counter that does not exist until it
    first increments makes those unevaluable at exactly the moment they
    matter — and an absent series looks identical to a healthy one, so
    the alert would silently never fire.
    """
    body = (await client.get("/internal/metrics")).text

    # Labelled *sample* lines, not HELP lines: a metric family emits a
    # HELP line even with no children, so asserting the latter would
    # pass against a metric exposing nothing at all.
    #
    # The value is deliberately not asserted. What matters is that the
    # series exists before its first event — pinning it to `0.0` would
    # make this test depend on no other test in the suite having
    # incremented the shared registry, which is a property of test
    # ordering rather than of the code under test.
    for series in (
        'agentverse_billing_webhooks_total{outcome="failed"}',
        "agentverse_billing_credit_drift_total ",
        'agentverse_quota_refusals_total{dimension="agent_runs"}',
        'agentverse_notification_deliveries_total{outcome="failed"}',
    ):
        assert series in body, f"{series} is not exposed — an alert on it could never fire"


async def test_every_billing_metric_named_in_a_rule_is_emitted_here(
    client: AsyncClient,
) -> None:
    """The half of the cross-check the worker cannot make.

    `promtool check rules` proves a rule's PromQL parses; it cannot know
    whether `agentverse_billing_credit_drift_total` is a metric this
    code emits or a plausible-looking name someone typed. A rule naming
    a metric nobody emits parses, loads, shows green — and can never
    fire.
    """
    body = (await client.get("/internal/metrics")).text
    exposed = set(re.findall(r"^(agentverse_[a-z_]+)", body, re.M))

    assert ALERTS_FILE.exists(), ALERTS_FILE
    referenced = set(re.findall(r"agentverse_billing_[a-z_]+", ALERTS_FILE.read_text()))
    referenced |= set(re.findall(r"agentverse_quota_[a-z_]+", ALERTS_FILE.read_text()))
    referenced |= set(re.findall(r"agentverse_payment_provider_[a-z_]+", ALERTS_FILE.read_text()))
    referenced |= set(re.findall(r"agentverse_notification_[a-z_]+", ALERTS_FILE.read_text()))
    assert referenced, "no billing metric referenced in alerts.yml"

    missing = {name for name in referenced if name not in exposed}
    assert not missing, f"alerts.yml references metrics apps/api never emits: {sorted(missing)}"


async def test_metrics_endpoint_is_absent_from_the_public_schema(
    client: AsyncClient,
) -> None:
    """Internal surface, kept out of the generated OpenAPI so it never
    reads as part of a contract anyone may depend on — and so a client
    generated from that schema cannot call it by accident.
    """
    schema = (await client.get("/openapi.json")).json()

    assert "/internal/metrics" not in schema["paths"]
