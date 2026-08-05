"""The referral loop: who referred whom, when it counts, and what each
side gets.

Two decisions carry this module.

**Qualification is a payment, not a signup.** A referral that pays out on
signup is a bounty on creating accounts, and it will be collected —
`growth-engineer`'s rule that a funnel stage must be a real behavioural
milestone is a fraud-resistance property here, not just a measurement
one. The referred workspace's first *successful payment* is the trigger,
which costs a real card to fake.

**Attribution is server-side and durable.** The referral row is written
when the referred workspace is created, from a code resolved on the
server. A client-only cookie is lost on a device switch and forged in a
console, and either failure lands directly in someone's balance.

Rewards are integer cents and are granted as account credit (Rule 15),
never as cash — credit is spendable on the product and costs the
platform its margin rather than its revenue.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ReferralStatus(StrEnum):
    """Where a referral is in its life.

    `PENDING` is the long tail: most referred workspaces sign up and
    never pay, and they stay pending forever rather than being deleted —
    the ratio of pending to qualified *is* the loop efficiency
    `growth-engineer` judges the loop by, and deleting the failures
    would make the loop look perfect.
    """

    PENDING = "pending"
    QUALIFIED = "qualified"
    REWARDED = "rewarded"
    #: Attribution existed but must not pay out — self-referral, a known
    #: abuse pattern, a refunded first payment. Kept rather than deleted
    #: so the reason survives.
    VOIDED = "voided"


_TRANSITIONS: dict[tuple[ReferralStatus, ReferralStatus], bool] = {
    (ReferralStatus.PENDING, ReferralStatus.QUALIFIED): True,
    (ReferralStatus.PENDING, ReferralStatus.VOIDED): True,
    (ReferralStatus.QUALIFIED, ReferralStatus.REWARDED): True,
    # A refund after the reward was granted. The credit is clawed back
    # by a separate ledger movement; this records that the referral
    # itself no longer stands.
    (ReferralStatus.QUALIFIED, ReferralStatus.VOIDED): True,
    (ReferralStatus.REWARDED, ReferralStatus.VOIDED): True,
}


class InvalidReferralTransitionError(Exception):
    """Maps to HTTP 409 — the request was well-formed but does not apply
    to this referral's current state.
    """

    def __init__(self, *, current: ReferralStatus, target: ReferralStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Cannot move a referral from {current.value!r} to {target.value!r}")


class SelfReferralError(Exception):
    """A workspace used its own code. Maps to HTTP 422.

    Refused at creation rather than voided later, so it never becomes a
    row someone has to explain. The obvious abuse, and the one worth
    making structurally impossible.
    """

    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id
        super().__init__("A workspace cannot refer itself")


def can_transition(*, current: ReferralStatus, target: ReferralStatus) -> bool:
    return _TRANSITIONS.get((current, target), False)


def assert_transition(*, current: ReferralStatus, target: ReferralStatus) -> None:
    if not can_transition(current=current, target=target):
        raise InvalidReferralTransitionError(current=current, target=target)


#: Credit granted to each side once a referral qualifies.
#:
#: Symmetric on purpose: an asymmetric reward makes the referrer's
#: recommendation feel like a sales pitch, and the referred party can see
#: the difference the moment they read the terms. $20 each is a full Pro
#: month's discount for the newcomer and meaningful for the referrer
#: without being worth farming.
REFERRER_REWARD_CENTS = 2000
REFERRED_REWARD_CENTS = 2000

#: How long referral credit stays spendable. Bounded so an inactive
#: workspace's promotional balance does not sit as an indefinite
#: liability, and long enough that a customer who refers a colleague in
#: January can still use it after a quiet spring.
REFERRAL_CREDIT_EXPIRY_DAYS = 365


@dataclass(frozen=True, slots=True)
class Referral:
    id: str
    #: The workspace whose code was used.
    referrer_workspace_id: str
    #: The workspace created with it. Unique across all referrals — a
    #: workspace can be referred once, and without that a code could be
    #: re-applied to farm rewards.
    referred_workspace_id: str
    code: str
    status: ReferralStatus
    referrer_reward_cents: int
    referred_reward_cents: int
    qualified_at: datetime | None
    rewarded_at: datetime | None
    voided_reason: str | None
    created_at: datetime

    @property
    def is_payable(self) -> bool:
        return self.status is ReferralStatus.QUALIFIED


def referral_code(workspace_id: str) -> str:
    """A workspace's stable, shareable code.

    Derived from the workspace id rather than stored, so it is the same
    every time it is displayed and needs no table of its own. Hashed
    rather than the raw id: the code appears in URLs people paste into
    public channels, and a raw workspace id there is an internal
    identifier leaked into the world.

    Eight uppercase hex characters — short enough to read aloud, and
    4 billion values against a workspace count that will not approach it,
    so guessing one is not a practical way to attribute a referral to a
    stranger. It is not a secret: worst case, someone credits a referral
    to a workspace that did not earn it, which is why qualification
    still requires a real payment.
    """
    digest = hashlib.sha256(f"agentverse-referral:{workspace_id}".encode()).hexdigest()
    return digest[:8].upper()


def resolve_reward(status: ReferralStatus) -> tuple[int, int]:
    """`(referrer_cents, referred_cents)` for a referral about to be paid.

    Reads the constants through a function so the amounts are resolved in
    one place — a campaign that changes them changes them for every
    call site at once, and a referral already rewarded keeps whatever it
    was granted because the amount is stored on its row.
    """
    if status is not ReferralStatus.QUALIFIED:
        return (0, 0)
    return (REFERRER_REWARD_CENTS, REFERRED_REWARD_CENTS)
