"""Coupons: codes that grant account credit.

**What these are not.** The payment provider already has promotion codes,
and M3 passes one straight through to checkout so it discounts the
subscription price at the provider. These coupons are a different
mechanism with no overlap: they grant **account credit**, which then
reduces what any future invoice collects. Two systems doing the same
thing would be the duplication Rule 3 forbids; two systems doing
different things need only a clear boundary, which this docstring is.

The practical difference a customer sees: a provider promotion code
changes the price of the plan they are buying right now, and a coupon
here puts money on their account that survives plan changes,
cancellation and resubscription.

Pure — no I/O. Every validity rule is a function over the coupon and the
moment, so "why was my code rejected" has one answer, computed the same
way in the API response and in a test.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class DiscountKind(StrEnum):
    """How a coupon's value is computed.

    `PERCENT_OFF` needs something to be a percentage *of*, which for a
    credit-granting coupon is the plan's price at redemption. Fixed
    amounts need nothing, which is why they are the safer default for a
    campaign — a percentage coupon redeemed against a plan whose price
    later changes grants a different amount than the campaign intended.
    """

    FIXED_CENTS = "fixed_cents"
    PERCENT_OFF = "percent_off"


class CouponRejection(StrEnum):
    """Why a code was refused.

    A closed set rather than free text so the UI can say something
    specific and actionable for each — "this code has expired" and "you
    have already used this code" need different next steps, and
    collapsing them into "invalid code" makes both unactionable.
    """

    UNKNOWN = "unknown_code"
    INACTIVE = "inactive"
    NOT_YET_VALID = "not_yet_valid"
    EXPIRED = "expired"
    EXHAUSTED = "redemption_limit_reached"
    ALREADY_REDEEMED = "already_redeemed_by_this_workspace"
    PLAN_NOT_ELIGIBLE = "plan_not_eligible"


class CouponRejectedError(Exception):
    """Maps to HTTP 422. Carries the specific reason, never a generic one."""

    def __init__(self, code: str, rejection: CouponRejection) -> None:
        self.code = code
        self.rejection = rejection
        super().__init__(f"Coupon {code!r} rejected: {rejection.value}")


class InvalidCouponError(ValueError):
    """The coupon's own configuration is incoherent."""


@dataclass(frozen=True, slots=True)
class Coupon:
    id: str
    #: Uppercase by convention and compared case-insensitively — a
    #: customer typing `welcome50` from a printed card should not fail.
    code: str
    kind: DiscountKind
    #: Cents for `FIXED_CENTS`, whole percent (1–100) for `PERCENT_OFF`.
    value: int
    description: str
    is_active: bool
    valid_from: datetime | None
    valid_until: datetime | None
    #: `None` means unlimited redemptions. Never a sentinel, matching the
    #: convention every other limit in this context uses.
    max_redemptions: int | None
    redemption_count: int
    #: Empty means every plan. A non-empty set restricts the coupon to
    #: those tiers — a campaign aimed at Pro should not silently apply to
    #: an Enterprise contract.
    eligible_plan_slugs: frozenset[str]
    #: How long the granted credit lasts. `None` means it never expires.
    credit_expires_after_days: int | None
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.code:
            raise InvalidCouponError("a coupon needs a code")
        if self.value <= 0:
            raise InvalidCouponError(
                f"coupon {self.code!r} must have a positive value, got {self.value}"
            )
        if self.kind is DiscountKind.PERCENT_OFF and self.value > 100:
            raise InvalidCouponError(
                f"coupon {self.code!r} discounts {self.value}% — a percentage above 100 "
                "would grant more credit than the plan costs"
            )
        if self.max_redemptions is not None and self.max_redemptions <= 0:
            raise InvalidCouponError(
                f"coupon {self.code!r} has max_redemptions={self.max_redemptions}; "
                "use None for unlimited rather than zero"
            )
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_until <= self.valid_from
        ):
            raise InvalidCouponError(f"coupon {self.code!r} expires at or before it becomes valid")


def normalize_code(code: str) -> str:
    """Codes are compared uppercase and trimmed.

    A customer copying a code out of an email routinely brings a
    trailing space with it, and rejecting that reads as a broken coupon
    rather than as a whitespace rule nobody told them about.
    """
    return code.strip().upper()


def validate(
    *,
    coupon: Coupon,
    now: datetime,
    plan_slug: str,
    already_redeemed: bool,
) -> CouponRejection | None:
    """`None` when the coupon may be redeemed, otherwise the reason.

    Checks run in the order a customer would find most useful: whether
    the code works at all, then whether it works *now*, then whether it
    works *for them*. A code that is both expired and already redeemed
    reports expiry, because that is the fact the customer cannot fix.
    """
    if not coupon.is_active:
        return CouponRejection.INACTIVE
    if coupon.valid_from is not None and now < coupon.valid_from:
        return CouponRejection.NOT_YET_VALID
    if coupon.valid_until is not None and now >= coupon.valid_until:
        return CouponRejection.EXPIRED
    if coupon.max_redemptions is not None and coupon.redemption_count >= coupon.max_redemptions:
        return CouponRejection.EXHAUSTED
    if already_redeemed:
        return CouponRejection.ALREADY_REDEEMED
    if coupon.eligible_plan_slugs and plan_slug not in coupon.eligible_plan_slugs:
        return CouponRejection.PLAN_NOT_ELIGIBLE
    return None


def credit_cents(*, coupon: Coupon, plan_price_cents: int | None) -> int:
    """How much credit redeeming this coupon grants.

    A percentage coupon needs a price to be a percentage of. `None`
    (a custom-priced tier) makes the percentage meaningless, and
    inventing a base would grant an arbitrary amount of real money —
    so it raises rather than guessing.

    Rounds **down**. The platform is giving money away here, and the
    residual sub-cent staying with the platform is the direction that
    cannot surprise anyone: a coupon never grants more than it says.
    """
    if coupon.kind is DiscountKind.FIXED_CENTS:
        return coupon.value
    if plan_price_cents is None:
        raise InvalidCouponError(
            f"coupon {coupon.code!r} is a percentage discount, but the plan has no "
            "published price to compute it against"
        )
    if plan_price_cents <= 0:
        return 0
    return (plan_price_cents * coupon.value) // 100
