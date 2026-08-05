"""Credit arithmetic, coupon validity, and the referral state machine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agentverse_api.billing_service.domain.coupon import (
    Coupon,
    CouponRejection,
    DiscountKind,
    InvalidCouponError,
    credit_cents,
    normalize_code,
    validate,
)
from agentverse_api.billing_service.domain.credit import (
    CreditReason,
    CreditTransaction,
    InsufficientCreditError,
    InvalidCreditAmountError,
    apply_credit,
    expired_amount,
    is_credit,
    next_balance,
)
from agentverse_api.billing_service.domain.referral import (
    InvalidReferralTransitionError,
    ReferralStatus,
    assert_transition,
    can_transition,
    referral_code,
    resolve_reward,
)

_NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


class TestCreditDirection:
    def test_every_reason_has_a_declared_direction(self) -> None:
        # Inferring direction from an amount's sign is what makes a
        # credit applied backwards possible; every reason must answer.
        for reason in CreditReason:
            assert isinstance(is_credit(reason), bool)

    def test_applying_to_an_invoice_is_a_debit(self) -> None:
        assert is_credit(CreditReason.INVOICE_APPLIED) is False

    def test_a_referral_reward_is_a_credit(self) -> None:
        assert is_credit(CreditReason.REFERRAL_REWARD) is True

    def test_expiry_is_a_debit(self) -> None:
        assert is_credit(CreditReason.EXPIRED) is False


class TestNextBalance:
    def test_a_grant_increases_the_balance(self) -> None:
        assert (
            next_balance(balance_cents=0, reason=CreditReason.REFERRAL_REWARD, amount_cents=2000)
            == 2000
        )

    def test_a_spend_decreases_the_balance(self) -> None:
        assert (
            next_balance(balance_cents=2000, reason=CreditReason.INVOICE_APPLIED, amount_cents=500)
            == 1500
        )

    def test_spending_the_whole_balance_is_allowed(self) -> None:
        assert (
            next_balance(balance_cents=2000, reason=CreditReason.INVOICE_APPLIED, amount_cents=2000)
            == 0
        )

    def test_over_spending_is_refused_not_allowed_negative(self) -> None:
        # A negative balance would mean the platform is owed money
        # through a mechanism with no way to collect it.
        with pytest.raises(InsufficientCreditError) as exc:
            next_balance(balance_cents=100, reason=CreditReason.INVOICE_APPLIED, amount_cents=101)
        assert exc.value.balance_cents == 100
        assert exc.value.requested_cents == 101

    def test_a_zero_movement_is_refused(self) -> None:
        # A ledger row that moves nothing is noise in the one record a
        # customer reads to understand their balance.
        with pytest.raises(InvalidCreditAmountError):
            next_balance(balance_cents=100, reason=CreditReason.PROMOTIONAL_GRANT, amount_cents=0)

    def test_a_negative_movement_is_refused(self) -> None:
        with pytest.raises(InvalidCreditAmountError):
            next_balance(balance_cents=100, reason=CreditReason.PROMOTIONAL_GRANT, amount_cents=-5)


class TestApplyCredit:
    def test_credit_covers_part_of_an_invoice(self) -> None:
        result = apply_credit(balance_cents=500, amount_due_cents=2900)
        assert result.applied_cents == 500
        assert result.remaining_due_cents == 2400
        assert result.remaining_balance_cents == 0

    def test_credit_larger_than_the_invoice_leaves_the_rest_on_account(self) -> None:
        # Never a negative invoice: no payment provider can charge -$30
        # and no customer can be paid from it.
        result = apply_credit(balance_cents=5000, amount_due_cents=2000)
        assert result.applied_cents == 2000
        assert result.remaining_due_cents == 0
        assert result.remaining_balance_cents == 3000

    def test_a_zero_invoice_consumes_nothing(self) -> None:
        result = apply_credit(balance_cents=5000, amount_due_cents=0)
        assert result.applied_cents == 0
        assert result.remaining_balance_cents == 5000

    def test_no_balance_consumes_nothing(self) -> None:
        result = apply_credit(balance_cents=0, amount_due_cents=2900)
        assert result.applied_cents == 0
        assert result.remaining_due_cents == 2900


class TestExpiry:
    def _grant(self, *, amount: int, expires: datetime | None) -> CreditTransaction:
        return CreditTransaction(
            id="tx-1",
            workspace_id="ws-1",
            reason=CreditReason.PROMOTIONAL_GRANT,
            amount_cents=amount,
            balance_after_cents=amount,
            description="",
            source_ref=None,
            expires_at=expires,
            created_at=_NOW,
        )

    def test_a_grant_with_no_expiry_never_expires(self) -> None:
        # The right default for a refund: money the customer already paid
        # should not evaporate.
        transactions = [self._grant(amount=1000, expires=None)]
        assert expired_amount(transactions=transactions, now=_NOW + timedelta(days=9999)) == 0

    def test_a_grant_past_its_expiry_counts(self) -> None:
        transactions = [self._grant(amount=1000, expires=_NOW)]
        assert expired_amount(transactions=transactions, now=_NOW) == 1000

    def test_a_grant_before_its_expiry_does_not_count(self) -> None:
        transactions = [self._grant(amount=1000, expires=_NOW + timedelta(days=1))]
        assert expired_amount(transactions=transactions, now=_NOW) == 0

    def test_debits_are_never_treated_as_expiring(self) -> None:
        spend = CreditTransaction(
            id="tx-2",
            workspace_id="ws-1",
            reason=CreditReason.INVOICE_APPLIED,
            amount_cents=500,
            balance_after_cents=500,
            description="",
            source_ref=None,
            expires_at=_NOW - timedelta(days=1),
            created_at=_NOW,
        )
        assert expired_amount(transactions=[spend], now=_NOW) == 0


def _coupon(**overrides: object) -> Coupon:
    kwargs: dict[str, object] = {
        "id": "coupon-1",
        "code": "WELCOME20",
        "kind": DiscountKind.FIXED_CENTS,
        "value": 2000,
        "description": "",
        "is_active": True,
        "valid_from": None,
        "valid_until": None,
        "max_redemptions": None,
        "redemption_count": 0,
        "eligible_plan_slugs": frozenset(),
        "credit_expires_after_days": None,
        "created_at": _NOW,
    }
    kwargs.update(overrides)
    return Coupon(**kwargs)  # type: ignore[arg-type]


class TestCouponConfiguration:
    def test_a_percentage_above_one_hundred_is_refused(self) -> None:
        # Free money with a typo as its only cause.
        with pytest.raises(InvalidCouponError, match="above 100"):
            _coupon(kind=DiscountKind.PERCENT_OFF, value=150)

    def test_a_zero_value_coupon_is_refused(self) -> None:
        with pytest.raises(InvalidCouponError):
            _coupon(value=0)

    def test_zero_max_redemptions_is_refused_in_favour_of_none(self) -> None:
        # Zero would read as "unlimited" to anyone who assumed falsy
        # means absent; `None` is the convention every other limit uses.
        with pytest.raises(InvalidCouponError, match="None for unlimited"):
            _coupon(max_redemptions=0)

    def test_an_expiry_before_its_start_is_refused(self) -> None:
        with pytest.raises(InvalidCouponError):
            _coupon(valid_from=_NOW, valid_until=_NOW - timedelta(days=1))


class TestCodeNormalization:
    def test_case_and_whitespace_are_normalized(self) -> None:
        # A customer copying a code out of an email routinely brings a
        # trailing space with it.
        assert normalize_code("  welcome20 ") == "WELCOME20"


class TestCouponValidity:
    def _validate(self, coupon: Coupon, **kwargs: object) -> CouponRejection | None:
        defaults: dict[str, object] = {
            "now": _NOW,
            "plan_slug": "pro",
            "already_redeemed": False,
        }
        defaults.update(kwargs)
        return validate(coupon=coupon, **defaults)  # type: ignore[arg-type]

    def test_a_valid_coupon_is_accepted(self) -> None:
        assert self._validate(_coupon()) is None

    def test_an_inactive_coupon_is_rejected(self) -> None:
        assert self._validate(_coupon(is_active=False)) is CouponRejection.INACTIVE

    def test_a_coupon_before_its_start_is_rejected(self) -> None:
        assert (
            self._validate(_coupon(valid_from=_NOW + timedelta(days=1)))
            is CouponRejection.NOT_YET_VALID
        )

    def test_a_coupon_at_its_expiry_is_rejected(self) -> None:
        assert self._validate(_coupon(valid_until=_NOW)) is CouponRejection.EXPIRED

    def test_an_exhausted_coupon_is_rejected(self) -> None:
        assert (
            self._validate(_coupon(max_redemptions=10, redemption_count=10))
            is CouponRejection.EXHAUSTED
        )

    def test_an_unlimited_coupon_is_never_exhausted(self) -> None:
        assert self._validate(_coupon(redemption_count=10_000)) is None

    def test_a_second_redemption_by_the_same_workspace_is_rejected(self) -> None:
        # Without this a fixed-cents coupon is an unlimited credit tap.
        assert self._validate(_coupon(), already_redeemed=True) is CouponRejection.ALREADY_REDEEMED

    def test_a_plan_outside_the_eligible_set_is_rejected(self) -> None:
        assert (
            self._validate(_coupon(eligible_plan_slugs=frozenset({"team"})))
            is CouponRejection.PLAN_NOT_ELIGIBLE
        )

    def test_an_empty_eligible_set_means_every_plan(self) -> None:
        assert self._validate(_coupon(), plan_slug="enterprise") is None

    def test_expiry_is_reported_before_already_redeemed(self) -> None:
        # A code that is both reports the fact the customer cannot fix.
        rejection = self._validate(_coupon(valid_until=_NOW), already_redeemed=True)
        assert rejection is CouponRejection.EXPIRED


class TestCouponValue:
    def test_a_fixed_coupon_grants_its_face_value(self) -> None:
        assert credit_cents(coupon=_coupon(), plan_price_cents=2900) == 2000

    def test_a_percentage_coupon_is_computed_against_the_plan_price(self) -> None:
        coupon = _coupon(kind=DiscountKind.PERCENT_OFF, value=50)
        assert credit_cents(coupon=coupon, plan_price_cents=2900) == 1450

    def test_a_percentage_rounds_down(self) -> None:
        # The platform is giving money away; the residual sub-cent
        # staying with the platform is the direction that surprises
        # nobody.
        coupon = _coupon(kind=DiscountKind.PERCENT_OFF, value=33)
        # 2900 * 33 / 100 = 957.0 exactly; 2999 * 33 / 100 = 989.67 -> 989.
        assert credit_cents(coupon=coupon, plan_price_cents=2999) == 989

    def test_a_percentage_against_a_free_plan_grants_nothing(self) -> None:
        coupon = _coupon(kind=DiscountKind.PERCENT_OFF, value=50)
        assert credit_cents(coupon=coupon, plan_price_cents=0) == 0

    def test_a_percentage_against_a_custom_priced_plan_raises(self) -> None:
        # Inventing a base would grant an arbitrary amount of real money.
        coupon = _coupon(kind=DiscountKind.PERCENT_OFF, value=50)
        with pytest.raises(InvalidCouponError, match="no\n?.*published price"):
            credit_cents(coupon=coupon, plan_price_cents=None)


class TestReferralCode:
    def test_the_code_is_stable_for_a_workspace(self) -> None:
        assert referral_code("ws-1") == referral_code("ws-1")

    def test_different_workspaces_get_different_codes(self) -> None:
        assert referral_code("ws-1") != referral_code("ws-2")

    def test_the_code_does_not_contain_the_workspace_id(self) -> None:
        # It appears in URLs people paste into public channels; a raw
        # workspace id there is an internal identifier leaked.
        workspace_id = "9f8e7d6c-1234-4321-abcd-1234567890ab"
        assert workspace_id not in referral_code(workspace_id)

    def test_the_code_is_short_and_uppercase(self) -> None:
        code = referral_code("ws-1")
        assert len(code) == 8
        assert code == code.upper()


class TestReferralTransitions:
    def test_a_pending_referral_can_qualify(self) -> None:
        assert can_transition(current=ReferralStatus.PENDING, target=ReferralStatus.QUALIFIED)

    def test_a_qualified_referral_can_be_rewarded(self) -> None:
        assert can_transition(current=ReferralStatus.QUALIFIED, target=ReferralStatus.REWARDED)

    def test_a_pending_referral_cannot_be_rewarded_directly(self) -> None:
        # Paying out without qualifying is paying for a signup, which is
        # the bounty this design exists to avoid.
        assert not can_transition(current=ReferralStatus.PENDING, target=ReferralStatus.REWARDED)

    def test_a_rewarded_referral_cannot_be_rewarded_again(self) -> None:
        with pytest.raises(InvalidReferralTransitionError):
            assert_transition(current=ReferralStatus.REWARDED, target=ReferralStatus.REWARDED)

    def test_every_status_except_voided_can_be_voided(self) -> None:
        for status in ReferralStatus:
            if status is ReferralStatus.VOIDED:
                continue
            assert can_transition(current=status, target=ReferralStatus.VOIDED)

    def test_a_voided_referral_is_terminal(self) -> None:
        for target in ReferralStatus:
            assert not can_transition(current=ReferralStatus.VOIDED, target=target)


class TestReferralReward:
    def test_only_a_qualified_referral_resolves_a_reward(self) -> None:
        assert resolve_reward(ReferralStatus.PENDING) == (0, 0)
        assert resolve_reward(ReferralStatus.REWARDED) == (0, 0)

    def test_a_qualified_referral_rewards_both_sides(self) -> None:
        referrer, referred = resolve_reward(ReferralStatus.QUALIFIED)
        assert referrer > 0
        assert referred > 0

    def test_the_reward_is_symmetric(self) -> None:
        # An asymmetric reward makes the referrer's recommendation feel
        # like a sales pitch, and the referred party can see the
        # difference the moment they read the terms.
        referrer, referred = resolve_reward(ReferralStatus.QUALIFIED)
        assert referrer == referred
