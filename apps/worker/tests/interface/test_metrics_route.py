"""`/internal/metrics` serves the Prometheus exposition format."""

from __future__ import annotations

import re
from pathlib import Path

from agentverse_shared.observability import billing_metrics
from httpx import AsyncClient

_OBSERVABILITY = Path(__file__).resolve().parents[4] / "infra" / "observability"

#: Checked-in alert rules, evaluated by the Prometheus in
#: `infra/docker-compose.yml` and by whatever runs them in staging.
ALERTS_FILE = _OBSERVABILITY / "alerts.yml"
#: The Grafana board. Same failure mode as a bad rule, quieter symptom:
#: a panel querying a metric nobody emits renders an empty graph, which
#: is indistinguishable from "no traffic".
DASHBOARD_FILE = _OBSERVABILITY / "grafana-dashboard.json"


async def test_metrics_endpoint_serves_the_exposition_format(client: AsyncClient) -> None:
    response = await client.get("/internal/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "agentverse_tool_calls_total" in response.text


async def test_metrics_endpoint_exposes_the_alertable_series(client: AsyncClient) -> None:
    """Every metric with a paging alert against it must be present from
    process start, not only after its first event.

    A counter that does not exist until it first increments makes
    `increase(...) > 0` unevaluable at exactly the moment it matters, and
    an alert on a missing series is an alert that silently never fires.
    """
    body = (await client.get("/internal/metrics")).text

    # A *sample* line, not just the HELP line a metric family emits even
    # with no children — the first version of this test asserted the
    # latter and would have passed against a metric exposing nothing.
    assert 'agentverse_egress_denied_total{range="metadata"} 0.0' in body
    assert "agentverse_credential_unseal_failures_total 0.0" in body
    assert 'agentverse_tool_calls_total{status="denied"} 0.0' in body


async def test_every_metric_named_in_a_rule_or_panel_is_actually_emitted(
    client: AsyncClient,
) -> None:
    """The gap `promtool` cannot close.

    `promtool check rules` validates syntax and PromQL parsing. It
    cannot know whether `agentverse_egress_denied_total` is a metric this
    code emits or a plausible-looking name someone typed. A rule
    referencing a metric that is never emitted parses fine, loads fine,
    shows green in the Prometheus UI — and can never fire. For the
    egress and credential rules, which exist precisely because their
    steady state is silence, that failure is indistinguishable from
    working correctly.

    So the rules are checked against the real exposition output.

    **Two services now emit metrics, and the check spans both.** The
    tool-execution surface comes from this process; the billing surface
    (Phase 9) comes from apps/api, which has its own
    `/internal/metrics`. The invariant is "no rule names a metric
    *nothing* emits" — not "this process emits everything" — so the
    billing families are resolved from their shared declaring module
    rather than from this endpoint. Asserting they appear here would
    force the worker to import metrics it does not produce, which would
    make the exposition claim something false.

    apps/api's own suite asserts that its endpoint actually serves those
    families, so neither half is taken on trust.
    """
    body = (await client.get("/internal/metrics")).text
    exposed = set(re.findall(r"^(agentverse_[a-z_]+)", body, re.M))

    # Families declared by the billing module. Read from the module's
    # own definitions rather than hardcoded, so a metric renamed there
    # does not silently drop out of this check.
    billing_families = {
        metric._name  # noqa: SLF001 - prometheus_client's only accessor for the base name
        for metric in vars(billing_metrics).values()
        if hasattr(metric, "_name") and str(getattr(metric, "_name", "")).startswith("agentverse_")
    }
    # A counter declared as `foo_total` is stored with `_name = "foo"`,
    # and rules reference the exposed `foo_total`. Accept both spellings.
    emitted_somewhere = exposed | billing_families | {f"{name}_total" for name in billing_families}

    for source in (ALERTS_FILE, DASHBOARD_FILE):
        assert source.exists(), source
        referenced = set(re.findall(r"agentverse_[a-z_]+", source.read_text()))
        assert referenced, f"no agentverse_* metric referenced in {source.name}"

        # `foo_bucket`/`_sum`/`_count` are histogram-derived series that
        # appear in the exposition under those exact names, so they need
        # no special handling — a counter's `foo_total` appears as
        # written too. Anything left unmatched is a genuine typo.
        missing = {name for name in referenced if name not in emitted_somewhere}
        assert not missing, f"{source.name} references metrics never emitted: {sorted(missing)}"


async def test_metrics_endpoint_is_absent_from_the_public_schema(client: AsyncClient) -> None:
    """Internal surface, kept out of the generated OpenAPI so it never
    reads as part of a contract anyone may depend on.
    """
    schema = (await client.get("/openapi.json")).json()

    assert "/internal/metrics" not in schema["paths"]
