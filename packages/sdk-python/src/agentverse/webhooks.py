"""Verifying an inbound AgentVerse webhook.

This is the highest-value thing in the SDK, because it is the piece every
customer would otherwise write themselves and the mistakes are silent:

- comparing signatures with `==`, which leaks the expected value one byte
  at a time to anyone who can measure the response time;
- ignoring the timestamp, which makes every captured delivery replayable
  forever;
- verifying the *parsed* body rather than the raw bytes, which fails the
  moment a customer's JSON library re-serializes with different spacing —
  and fails in a way that looks like our signatures being wrong.

`verify_webhook` takes the raw body precisely so the third mistake is
hard to make: the signature is over bytes, so the argument is bytes.

Example:

    from agentverse.webhooks import verify_webhook, SignatureVerificationError

    @app.post("/webhooks/agentverse")
    async def receive(request):
        try:
            event = verify_webhook(
                payload=await request.body(),
                signature_header=request.headers["AgentVerse-Signature"],
                secret=os.environ["AGENTVERSE_WEBHOOK_SECRET"],
            )
        except SignatureVerificationError:
            return Response(status_code=400)
        ...
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

SIGNATURE_HEADER = "AgentVerse-Signature"
SIGNATURE_VERSION = "v1"

#: How far out of date a delivery may be before it is rejected. Five
#: minutes is generous enough for a receiver behind a slow queue and
#: short enough that a captured delivery stops being useful quickly.
DEFAULT_TOLERANCE_SECONDS = 300


class SignatureVerificationError(Exception):
    """The delivery is not one we sent, or is too old to accept.

    One exception for both, deliberately. A receiver that answers
    differently for "bad signature" and "stale timestamp" tells an
    attacker which half of their forgery to fix.
    """


@dataclass(frozen=True)
class WebhookEvent:
    """A verified delivery.

    `data` is the event-specific body; everything above it is the
    envelope every event shares, so a receiver can route on `type` and
    dedupe on `id` without knowing which event it is.
    """

    id: str
    type: str
    api_version: str
    created_at: str
    data: dict[str, Any]


def _parse_header(header: str) -> tuple[int, list[str]]:
    """Pull the timestamp and every version's digest out of the header.

    Returns *all* `v1=` values rather than the first: the header format
    allows several so a secret rotation can be signed under both, and a
    parser that read only the first would reject half the deliveries
    during exactly the window rotation exists to make safe.
    """
    timestamp: int | None = None
    signatures: list[str] = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError as exc:
                raise SignatureVerificationError("Malformed timestamp in signature header") from exc
        elif key == SIGNATURE_VERSION:
            signatures.append(value)
    if timestamp is None or not signatures:
        raise SignatureVerificationError("Signature header is missing a timestamp or a digest")
    return timestamp, signatures


def compute_signature(*, payload: bytes, secret: str, timestamp: int) -> str:
    """The expected digest for a delivery.

    Exposed so a caller can verify against their own transport, and so
    the construction is documented by code rather than by prose that can
    drift from it.
    """
    signed = b"%d." % timestamp + payload
    return hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def verify_webhook(
    *,
    payload: bytes | str,
    signature_header: str,
    secret: str,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: float | None = None,
) -> WebhookEvent:
    """Verify a delivery and return it parsed. Raises on any failure.

    `payload` must be the **raw** body. Passing a re-serialized dict is
    the most common way to break this: the signature is over bytes, and a
    JSON library that spaces its output differently produces a different
    digest even for an identical object.
    """
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    timestamp, signatures = _parse_header(signature_header)

    current = time.time() if now is None else now
    if tolerance_seconds > 0 and abs(current - timestamp) > tolerance_seconds:
        # Rejected *before* the digest is compared, so a stale delivery
        # costs nothing to discard. `abs` catches clocks in both
        # directions: a receiver whose clock runs fast would otherwise
        # accept a delivery from its own future indefinitely.
        raise SignatureVerificationError(
            f"Delivery timestamp is outside the {tolerance_seconds}s tolerance"
        )

    expected = compute_signature(payload=raw, secret=secret, timestamp=timestamp)
    # `compare_digest`, not `==`. An early-exit comparison leaks the
    # expected value one byte at a time to anyone who can measure how
    # long the response takes.
    if not any(hmac.compare_digest(expected, provided) for provided in signatures):
        raise SignatureVerificationError("Signature does not match")

    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SignatureVerificationError("Verified payload is not valid JSON") from exc
    if not isinstance(body, dict):
        raise SignatureVerificationError("Verified payload is not an object")

    # A receiver should not have to guard `event.data` for `None` on an
    # event that happens to carry no body.
    data = body.get("data")
    return WebhookEvent(
        id=str(body.get("id", "")),
        type=str(body.get("type", "")),
        api_version=str(body.get("api_version", "")),
        created_at=str(body.get("created_at", "")),
        data=data if isinstance(data, dict) else {},
    )
