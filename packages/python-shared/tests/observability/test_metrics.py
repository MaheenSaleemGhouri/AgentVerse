"""The cardinality guarantee is the thing worth testing here.

A metric that counts slightly wrong is a nuisance. A metric that mints a
new time series per tenant, or per tool name a third-party server
invents, takes the monitoring system down — and it does so gradually,
under exactly the load where you need it. So most of these tests are
about what the module *refuses* to do.
"""

from __future__ import annotations

from prometheus_client import REGISTRY

from agentverse_shared.observability import metrics
from agentverse_shared.security.egress_guard import EGRESS_RANGE_SAMPLES, classify_address


def _value(name: str, **labels: str) -> float:
    got = REGISTRY.get_sample_value(name, labels or None)
    return 0.0 if got is None else got


def test_tool_call_records_status_duration_and_overhead() -> None:
    before = _value("agentverse_tool_calls_total", status="success")

    metrics.record_tool_call(status="success", duration_seconds=1.5, overhead_seconds=0.01)

    assert _value("agentverse_tool_calls_total", status="success") == before + 1


def test_refusal_increments_both_the_status_and_the_reason() -> None:
    """A denial is a tool call *and* a denial.

    Counting it only as a denial would make the call-rate panel
    under-report traffic; counting it only as a status would make the
    "which control fired" panel impossible.
    """
    status_before = _value("agentverse_tool_calls_total", status="denied")
    reason_before = _value("agentverse_tool_calls_denied_total", reason="permission")

    metrics.record_tool_call(
        status="denied",
        duration_seconds=0.01,
        overhead_seconds=0.01,
        denial_reason="permission",
    )

    assert _value("agentverse_tool_calls_total", status="denied") == status_before + 1
    assert _value("agentverse_tool_calls_denied_total", reason="permission") == reason_before + 1


def test_unknown_status_collapses_to_other_rather_than_minting_a_series() -> None:
    before = _value("agentverse_tool_calls_total", status="other")

    metrics.record_tool_call(
        status="ws_01ABCDEF_some_unexpected_value",
        duration_seconds=0.1,
        overhead_seconds=0.1,
    )

    assert _value("agentverse_tool_calls_total", status="other") == before + 1
    assert (
        REGISTRY.get_sample_value(
            "agentverse_tool_calls_total", {"status": "ws_01ABCDEF_some_unexpected_value"}
        )
        is None
    )


def test_attacker_controlled_tool_name_cannot_reach_a_label() -> None:
    """A custom MCP server declares its own tool names.

    If one of those reached a label, a server advertising ten thousand
    tools would mint ten thousand series — our monitoring, taken down by
    a customer's server. The API is the defence: there is no parameter
    to pass a tool name into.
    """
    import inspect

    parameters = set(inspect.signature(metrics.record_tool_call).parameters)

    assert "tool_name" not in parameters
    assert "workspace_id" not in parameters
    assert "installed_server_id" not in parameters


def test_denial_reason_free_text_does_not_become_a_label() -> None:
    """The boundary's denial reasons embed tool names.

    `"tool 'delete_repo' is not in this agent's allowed-tool list"` is a
    perfectly good sentence for `tool_calls.denial_reason` and a
    catastrophic label value.
    """
    before = _value("agentverse_tool_calls_denied_total", reason="other")

    metrics.record_tool_call(
        status="denied",
        duration_seconds=0.01,
        overhead_seconds=0.01,
        denial_reason="tool 'delete_repo' is not in this agent's allowed-tool list",
    )

    assert _value("agentverse_tool_calls_denied_total", reason="other") == before + 1


def test_negative_durations_are_clamped() -> None:
    """`overhead = elapsed - excluded` can go marginally negative from
    monotonic-clock rounding. A negative observation would corrupt the
    histogram's sum permanently, so it is clamped rather than trusted.
    """
    metrics.record_tool_call(status="success", duration_seconds=-1.0, overhead_seconds=-1.0)

    total = _value("agentverse_tool_call_duration_seconds_sum")
    assert total >= 0.0


def test_every_egress_range_the_guard_can_produce_is_a_known_label() -> None:
    """The two modules must agree, and nothing enforces that but this.

    `classify_address` lives in the security package and the vocabulary
    lives in the metrics package. A range added to the guard without a
    category here would silently become `other` — the denial would still
    happen, but the dashboard would stop distinguishing a metadata probe
    from a LAN address.
    """
    for address in EGRESS_RANGE_SAMPLES:
        assert classify_address(address) in metrics.EGRESS_RANGES, address


def test_metadata_address_is_not_counted_as_link_local() -> None:
    """169.254.169.254 sits inside 169.254.0.0/16.

    Collapsing them would bury a credential-theft probe among ordinary
    misconfigured LAN addresses — and the metadata alert pages at a
    single event precisely because it should never fire otherwise.
    """
    assert classify_address("169.254.169.254") == "metadata"
    assert classify_address("169.254.1.1") == "link_local"


def test_ipv4_mapped_metadata_address_still_classifies_as_metadata() -> None:
    """`::ffff:169.254.169.254` is the metadata address wearing a hat.

    The guard already denies it; this asserts the *label* survives
    normalisation too, so the alert fires on the v6-wrapped form.
    """
    assert classify_address("::ffff:169.254.169.254") == "metadata"


def test_render_latest_emits_the_exposition_format() -> None:
    metrics.record_tool_call(status="success", duration_seconds=0.1, overhead_seconds=0.01)

    body = metrics.render_latest().decode()

    assert "agentverse_tool_calls_total" in body
    assert "# TYPE agentverse_tool_calls_total counter" in body


def test_no_agentverse_metric_carries_a_tenant_label() -> None:
    """The scrape endpoint is internal, but "internal" is a network
    property that can be misconfigured. Nothing tenant-identifying is in
    the payload in the first place.

    Asserted against the collected *label names* rather than by
    substring-searching the rendered text: the first version of this test
    did the latter and failed on the words appearing in a HELP string,
    which is documentation, not data.
    """
    forbidden = {"workspace_id", "installed_server_id", "tool_name", "run_id", "agent_id"}

    seen: set[str] = set()
    for metric in REGISTRY.collect():
        if not metric.name.startswith("agentverse_"):
            continue
        for sample in metric.samples:
            seen.update(sample.labels)

    assert seen & forbidden == set()
    # And the guard is meaningful — these metrics do carry labels.
    assert "status" in seen
