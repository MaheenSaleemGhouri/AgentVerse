"""`/internal/metrics` serves the Prometheus exposition format."""

from __future__ import annotations

import re
from pathlib import Path

from httpx import AsyncClient

#: Checked-in alert rules, evaluated by the Prometheus in
#: `infra/docker-compose.yml` and by whatever runs them in staging.
ALERTS_FILE = Path(__file__).resolve().parents[4] / "infra" / "observability" / "alerts.yml"


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


async def test_every_metric_named_in_an_alert_rule_is_actually_emitted(
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
    """
    assert ALERTS_FILE.exists(), ALERTS_FILE

    referenced = set(re.findall(r"agentverse_[a-z_]+", ALERTS_FILE.read_text()))
    assert referenced, "no agentverse_* metric referenced — the regex or the file moved"

    body = (await client.get("/internal/metrics")).text
    exposed = set(re.findall(r"^(agentverse_[a-z_]+)", body, re.M))

    missing = {
        name
        for name in referenced
        # `foo_bucket`/`_sum`/`_count` are histogram-derived series that
        # appear in the exposition under those exact names, so they need
        # no special handling — but `foo_total` for a counter appears as
        # written too. Anything left unmatched is a genuine typo.
        if name not in exposed
    }
    assert not missing, f"alert rules reference metrics that are never emitted: {sorted(missing)}"


async def test_metrics_endpoint_is_absent_from_the_public_schema(client: AsyncClient) -> None:
    """Internal surface, kept out of the generated OpenAPI so it never
    reads as part of a contract anyone may depend on.
    """
    schema = (await client.get("/openapi.json")).json()

    assert "/internal/metrics" not in schema["paths"]
