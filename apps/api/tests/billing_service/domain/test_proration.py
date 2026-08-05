"""Proration arithmetic.

Every assertion here is about real money, so the numbers are worked out
by hand in the comments rather than computed by the same expression the
implementation uses — a test that recomputes the implementation proves
only that Python is deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agentverse_api.billing_service.domain.proration import (
    InvalidBillingPeriodError,
    prorate,
)

# A 30-day period, so "half the period" is exactly 15 days and the
# arithmetic is checkable in your head.
_START = datetime(2026, 6, 1, tzinfo=UTC)
_END = datetime(2026, 7, 1, tzinfo=UTC)
_MID = datetime(2026, 6, 16, tzinfo=UTC)

_PRO = 2900
_TEAM = 9900


class TestUpgrade:
    def test_halfway_upgrade_credits_and_charges_half(self) -> None:
        result = prorate(
            old_price_cents=_PRO,
            new_price_cents=_TEAM,
            period_start=_START,
            period_end=_END,
            change_at=_MID,
        )
        # 15 of 30 days remain. Credit: 2900 * 1/2 = 1450 exactly.
        # Charge: 9900 * 1/2 = 4950 exactly. Net owed: 3500.
        assert result.unused_credit_cents == 1450
        assert result.prorated_charge_cents == 4950
        assert result.net_cents == 3500

    def test_a_change_at_the_period_start_prorates_the_whole_period(self) -> None:
        result = prorate(
            old_price_cents=_PRO,
            new_price_cents=_TEAM,
            period_start=_START,
            period_end=_END,
            change_at=_START,
        )
        assert result.unused_credit_cents == _PRO
        assert result.prorated_charge_cents == _TEAM

    def test_a_change_at_the_period_end_prorates_nothing(self) -> None:
        result = prorate(
            old_price_cents=_PRO,
            new_price_cents=_TEAM,
            period_start=_START,
            period_end=_END,
            change_at=_END,
        )
        assert result.unused_credit_cents == 0
        assert result.prorated_charge_cents == 0
        assert result.net_cents == 0


class TestDowngrade:
    def test_a_mid_cycle_downgrade_produces_a_negative_net(self) -> None:
        result = prorate(
            old_price_cents=_TEAM,
            new_price_cents=_PRO,
            period_start=_START,
            period_end=_END,
            change_at=_MID,
        )
        # 4950 credited, 1450 charged: the customer is owed 3500. A
        # credit against the next invoice, never an automatic refund.
        assert result.net_cents == -3500


class TestRounding:
    def test_rounding_never_favors_the_platform(self) -> None:
        # A price and a fraction chosen so both lines have a remainder:
        # 1 day of a 30-day period at 1000c is 33.33c.
        change_at = _END - timedelta(days=1)
        result = prorate(
            old_price_cents=1000,
            new_price_cents=1000,
            period_start=_START,
            period_end=_END,
            change_at=change_at,
        )
        # Credit rounds up (34), charge rounds down (33). The residual
        # cent lands with the customer, so a same-price change can never
        # cost them money.
        assert result.unused_credit_cents == 34
        assert result.prorated_charge_cents == 33
        assert result.net_cents == -1

    def test_a_same_plan_change_never_charges_the_customer(self) -> None:
        # Property version of the above: for any moment in the period,
        # changing to the same price is never net-positive.
        for day in range(31):
            result = prorate(
                old_price_cents=2999,
                new_price_cents=2999,
                period_start=_START,
                period_end=_END,
                change_at=_START + timedelta(days=day),
            )
            assert result.net_cents <= 0


class TestDeterminism:
    def test_recomputing_from_the_same_inputs_reproduces_the_cents(self) -> None:
        # The property that makes a stored proration auditable months
        # later: nothing in the calculation reads a clock.
        args = {
            "old_price_cents": 2900,
            "new_price_cents": 9900,
            "period_start": _START,
            "period_end": _END,
            "change_at": _START + timedelta(days=7, hours=13, minutes=41),
        }
        first = prorate(**args)  # type: ignore[arg-type]
        second = prorate(**args)  # type: ignore[arg-type]
        assert first == second

    def test_shorter_months_are_priced_as_shorter_service(self) -> None:
        # Exact second-based math, not rounded months: half of February
        # and half of March are both half, but a *day* is worth more in
        # February.
        feb_result = prorate(
            old_price_cents=0,
            new_price_cents=2800,
            period_start=datetime(2026, 2, 1, tzinfo=UTC),
            period_end=datetime(2026, 3, 1, tzinfo=UTC),
            change_at=datetime(2026, 2, 27, tzinfo=UTC),
        )
        mar_result = prorate(
            old_price_cents=0,
            new_price_cents=2800,
            period_start=datetime(2026, 3, 1, tzinfo=UTC),
            period_end=datetime(2026, 4, 1, tzinfo=UTC),
            change_at=datetime(2026, 3, 27, tzinfo=UTC),
        )
        # Two days left of 28 vs. five days left of 31: 2800 * 2/28 = 200
        # exactly, and 2800 * 5/31 = 451.6 truncated to 451. A day in
        # February is worth 100c of this plan and a day in March 90c —
        # which is the point. Rounded-month math would price both the
        # same and quietly overcharge the February customer.
        assert feb_result.prorated_charge_cents == 200
        assert mar_result.prorated_charge_cents == 451


class TestValidation:
    def test_a_change_before_its_period_is_refused(self) -> None:
        # Clamping instead would turn a clock-skew or replayed-event bug
        # into a plausible invoice nobody questions.
        with pytest.raises(InvalidBillingPeriodError):
            prorate(
                old_price_cents=_PRO,
                new_price_cents=_TEAM,
                period_start=_START,
                period_end=_END,
                change_at=_START - timedelta(seconds=1),
            )

    def test_a_change_after_its_period_is_refused(self) -> None:
        with pytest.raises(InvalidBillingPeriodError):
            prorate(
                old_price_cents=_PRO,
                new_price_cents=_TEAM,
                period_start=_START,
                period_end=_END,
                change_at=_END + timedelta(seconds=1),
            )

    def test_an_inverted_period_is_refused(self) -> None:
        with pytest.raises(InvalidBillingPeriodError):
            prorate(
                old_price_cents=_PRO,
                new_price_cents=_TEAM,
                period_start=_END,
                period_end=_START,
                change_at=_START,
            )

    def test_a_negative_price_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must not be negative"):
            prorate(
                old_price_cents=-1,
                new_price_cents=_TEAM,
                period_start=_START,
                period_end=_END,
                change_at=_MID,
            )


class TestReporting:
    def test_remaining_fraction_is_reported_in_parts_per_million(self) -> None:
        result = prorate(
            old_price_cents=_PRO,
            new_price_cents=_TEAM,
            period_start=_START,
            period_end=_END,
            change_at=_MID,
        )
        assert result.remaining_fraction_ppm == 500_000
