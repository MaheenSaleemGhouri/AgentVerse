"""Validating the `plans` table's JSON columns.

The bug class every test here guards against is the same one: a
malformed plan row that parses into something *permissive*. `None` means
unlimited in this system, so a typo'd key silently grants unlimited
access rather than failing.
"""

from __future__ import annotations

import pytest

from agentverse_api.billing_service.domain.plan import (
    Capability,
    MeteredDimension,
    PlanTier,
    ResourceLimit,
)
from agentverse_api.billing_service.infrastructure.plan_config import (
    MalformedPlanError,
    to_domain,
)


def _to_domain(**overrides: object) -> object:
    kwargs: dict[str, object] = {
        "plan_id": "plan-1",
        "slug": PlanTier.PRO,
        "display_name": "Pro",
        "description": "For builders.",
        "monthly_price_cents": 2_900,
        "annual_price_cents": 29_000,
        "currency": "usd",
        "trial_days": 14,
        "is_public": True,
        "is_active": True,
        "sort_order": 1,
        "resource_limits": {"agents": 25},
        "metered_allowances": {"agent_runs": 10_000},
        "capabilities": ["analytics"],
        "overage_rates": {
            "agent_runs": {"billing_increment": 1_000, "price_cents_per_increment": 300}
        },
    }
    kwargs.update(overrides)
    return to_domain(**kwargs)  # type: ignore[arg-type]


class TestHappyPath:
    def test_parses_a_well_formed_row(self) -> None:
        plan = _to_domain()
        assert plan.resource_limit(ResourceLimit.AGENTS) == 25  # type: ignore[attr-defined]
        assert plan.metered_allowance(MeteredDimension.AGENT_RUNS) == 10_000  # type: ignore[attr-defined]
        assert plan.grants(Capability.ANALYTICS) is True  # type: ignore[attr-defined]

    def test_null_limit_survives_as_unlimited(self) -> None:
        plan = _to_domain(resource_limits={"agents": None})
        assert plan.resource_limit(ResourceLimit.AGENTS) is None  # type: ignore[attr-defined]

    def test_currency_is_normalised_to_lowercase(self) -> None:
        # Stripe rejects uppercase currency codes. Normalising on read
        # means a row inserted as "USD" does not fail at checkout.
        plan = _to_domain(currency="USD")
        assert plan.currency == "usd"  # type: ignore[attr-defined]


class TestRejectsPermissiveMalformations:
    def test_unknown_resource_limit_key_is_an_error(self) -> None:
        # `"agent"` for `"agents"` would leave AGENTS unset, which this
        # system reads as unlimited — a typo granting unlimited agents.
        with pytest.raises(MalformedPlanError, match="unknown resource limit 'agent'"):
            _to_domain(resource_limits={"agent": 25})

    def test_unknown_metered_dimension_is_an_error(self) -> None:
        with pytest.raises(MalformedPlanError, match="unknown metered dimension"):
            _to_domain(metered_allowances={"agent_run": 10})

    def test_unknown_capability_is_an_error(self) -> None:
        # Silently dropping it would leave a plan advertising a feature
        # on the pricing page that enforcement never grants.
        with pytest.raises(MalformedPlanError, match="unknown capability"):
            _to_domain(capabilities=["telepathy"])

    def test_boolean_limit_is_rejected_rather_than_read_as_one(self) -> None:
        # `bool` subclasses `int` in Python, so `true` would otherwise
        # parse as the limit 1 — a plan capped at one agent from a value
        # that was never a number.
        with pytest.raises(MalformedPlanError, match="must be an integer or null"):
            _to_domain(resource_limits={"agents": True})

    def test_string_limit_is_rejected(self) -> None:
        with pytest.raises(MalformedPlanError, match="must be an integer or null"):
            _to_domain(resource_limits={"agents": "25"})

    def test_negative_limit_is_rejected(self) -> None:
        with pytest.raises(MalformedPlanError, match="must not be negative"):
            _to_domain(resource_limits={"agents": -1})

    def test_non_object_limits_column_is_rejected(self) -> None:
        with pytest.raises(MalformedPlanError, match="must be an object"):
            _to_domain(resource_limits=[])

    def test_capabilities_must_be_an_array(self) -> None:
        with pytest.raises(MalformedPlanError, match="must be an array"):
            _to_domain(capabilities={"analytics": True})


class TestOverageRateValidation:
    def test_extra_key_in_an_overage_rate_is_rejected(self) -> None:
        # A renamed field must fail loudly here, not be dropped and leave
        # the rate reading as a default.
        with pytest.raises(MalformedPlanError, match="overage rate"):
            _to_domain(
                overage_rates={
                    "agent_runs": {
                        "billing_increment": 1_000,
                        "price_cents_per_increment": 300,
                        "discount": 10,
                    }
                }
            )

    def test_zero_billing_increment_is_rejected(self) -> None:
        with pytest.raises(MalformedPlanError, match="overage rate"):
            _to_domain(
                overage_rates={
                    "agent_runs": {"billing_increment": 0, "price_cents_per_increment": 300}
                }
            )

    def test_negative_price_is_rejected(self) -> None:
        with pytest.raises(MalformedPlanError, match="overage rate"):
            _to_domain(
                overage_rates={
                    "agent_runs": {"billing_increment": 1_000, "price_cents_per_increment": -1}
                }
            )


class TestScalarValidation:
    def test_negative_price_column_is_rejected(self) -> None:
        with pytest.raises(MalformedPlanError):
            _to_domain(monthly_price_cents=-100)

    def test_empty_display_name_is_rejected(self) -> None:
        with pytest.raises(MalformedPlanError):
            _to_domain(display_name="")
