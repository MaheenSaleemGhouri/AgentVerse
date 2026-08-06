"""Signing outbound webhooks, and the retry schedule for delivering them.

Pure — no I/O, no clock beyond what is passed in.

**The signature covers a timestamp as well as the body.** A signature
over the body alone is replayable forever: anyone who captures one
delivery can resend it to the customer's endpoint indefinitely, and it
verifies every time. Signing `{timestamp}.{body}` and having the
receiver reject old timestamps bounds that window. This is the same
construction Stripe uses, deliberately — customers already have code
that verifies it, and inventing a different scheme would mean every
integration writes new verification logic for no gain.

**Comparison is constant-time.** A verifier that returns early on the
first differing byte leaks the expected signature one byte at a time to
anyone who can measure it. `hmac.compare_digest` exists for this and the
helper here uses it, so the correct comparison is the convenient one.

**Retries are capped, spread, and jittered.** Uncapped retries against a
customer endpoint that has been down for a week are a queue that never
drains. Jitter matters because without it every delivery that failed
during one outage retries at the same instant when the endpoint
recovers — the platform would be the thing that knocks it over again.
"""

from __future__ import annotations

import hashlib
import hmac
import random
from dataclasses import dataclass

#: Signature scheme version, carried in the header. A future change to
#: the construction adds `v2=` alongside `v1=` rather than replacing it,
#: so a customer's verifier keeps working through the transition.
SIGNATURE_VERSION = "v1"

#: How far out of date a delivery's timestamp may be before a receiver
#: should reject it. Documented rather than enforced here — it is the
#: *receiver's* check, and stating the number is what makes their
#: verifier writable.
RECOMMENDED_TOLERANCE_SECONDS = 300


def signing_payload(*, timestamp: int, body: str) -> str:
    """Exactly what the HMAC covers.

    A single function so the sender and the documentation cannot
    describe two different constructions — the failure mode being that
    every customer's verifier fails and nobody can tell whose bug it is.
    """
    return f"{timestamp}.{body}"


def sign(*, secret: str, timestamp: int, body: str) -> str:
    """The hex digest for one delivery."""
    return hmac.new(
        secret.encode("utf-8"),
        signing_payload(timestamp=timestamp, body=body).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def signature_header(*, secret: str, timestamp: int, body: str) -> str:
    """The full header value: `t=<unix>,v1=<hex>`.

    Version-prefixed so a second scheme can be sent alongside the first
    during a migration rather than replacing it.
    """
    digest = sign(secret=secret, timestamp=timestamp, body=body)
    return f"t={timestamp},{SIGNATURE_VERSION}={digest}"


def verify(*, secret: str, timestamp: int, body: str, provided: str) -> bool:
    """Constant-time check of a signature we produced.

    Lives here rather than only in the docs so our own tests verify
    through the same code path a customer would — a signer with no
    verifier beside it is a signer nobody has checked.
    """
    expected = sign(secret=secret, timestamp=timestamp, body=body)
    return hmac.compare_digest(expected, provided)


#: Delivery attempts before a webhook is abandoned. Six attempts spread
#: over roughly two hours: long enough to ride out a deploy or a restart,
#: short enough that a permanently dead endpoint stops consuming the
#: queue the same afternoon.
MAX_ATTEMPTS = 6

#: Base delays in seconds, one per attempt already made. Explicit rather
#: than computed so the schedule is readable and a change to it is a
#: visible diff instead of an exponent someone has to evaluate.
_BACKOFF_SECONDS: tuple[int, ...] = (10, 60, 300, 900, 3_600)


class DeliveryExhaustedError(Exception):
    """No attempts remain. Maps to a `failed` delivery, not a retry."""


def backoff_seconds(*, attempt: int, jitter: random.Random | None = None) -> int:
    """How long to wait before attempt number `attempt` (1-based).

    Jittered by up to ±20%. Without it, every delivery that failed during
    one outage retries at the same instant when the endpoint recovers,
    and the platform becomes the thing that knocks it over again.
    """
    if attempt < 1:
        raise ValueError("attempt is 1-based")
    if attempt > len(_BACKOFF_SECONDS):
        raise DeliveryExhaustedError(f"No attempt {attempt}; the schedule has {MAX_ATTEMPTS}")
    base = _BACKOFF_SECONDS[attempt - 1]
    source = jitter or random
    spread = int(base * 0.2)
    return max(base + source.randint(-spread, spread), 1)


def should_retry(*, attempts_made: int, response_status: int | None) -> bool:
    """Is another attempt worth making?

    A `4xx` other than 408 and 429 is the endpoint saying the request
    itself is wrong — the same bytes will be rejected the same way in an
    hour, so retrying is pure noise for both sides. A timeout (no status
    at all), a 5xx, a 408 or a 429 are all "not now", and those retry.
    """
    if attempts_made >= MAX_ATTEMPTS:
        return False
    if response_status is None:
        return True
    if response_status in (408, 429):
        return True
    return not 400 <= response_status < 500


def is_success(status_code: int) -> bool:
    """Any 2xx. A 3xx is not success: the guard does not follow redirects
    for webhook delivery, and treating one as delivered would mean
    silently accepting that the payload went somewhere unverified.
    """
    return 200 <= status_code < 300


@dataclass(frozen=True, slots=True)
class DeliveryOutcome:
    """What one attempt produced, and what happens next."""

    delivered: bool
    retry: bool
    attempts_made: int
    response_status: int | None
    error: str | None


def evaluate_attempt(
    *, attempts_made: int, response_status: int | None, error: str | None
) -> DeliveryOutcome:
    """Turn one attempt's result into the delivery's next state."""
    delivered = response_status is not None and is_success(response_status)
    return DeliveryOutcome(
        delivered=delivered,
        retry=(
            not delivered
            and should_retry(attempts_made=attempts_made, response_status=response_status)
        ),
        attempts_made=attempts_made,
        response_status=response_status,
        error=error,
    )
