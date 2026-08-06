"""Verifying an inbound webhook.

The three mistakes this function exists to prevent are all silent, so
they are what these tests are about: a forged signature accepted, a
captured delivery replayed forever, and a signature checked against
re-serialized JSON instead of the bytes that were signed.

The expected digests are the same literals the platform's own suites pin
(`apps/api` and `apps/worker`). If they diverge, a customer using this
SDK cannot verify a real delivery — which looks, from their side, exactly
like our signatures being broken.
"""

from __future__ import annotations

import json
import time

import pytest

from agentverse.webhooks import (
    DEFAULT_TOLERANCE_SECONDS,
    SignatureVerificationError,
    compute_signature,
    verify_webhook,
)

_SECRET = "whsec_deadbeef"
_TIMESTAMP = 1_800_000_000
_BODY = b'{"id":"evt_1","type":"run.completed"}'

#: Pinned against the platform. Identical literals live in
#: `apps/api/tests/webhook_service/domain/test_signing_and_retries.py`
#: and `apps/worker/tests/webhooks/test_signing_contract.py`.
EXPECTED_EMPTY_OBJECT = "bdbde3be09b48f018e8bfbaaaceadc664aaee6bbc7a1d2489d33f0f50c9e674c"
EXPECTED_EVENT = "53e42645290d85bfbc1615823cb3bcb7a956c8b7c1ce9d2704a9de4337136e56"


def _header(*, secret: str = _SECRET, timestamp: int = _TIMESTAMP, body: bytes = _BODY) -> str:
    return f"t={timestamp},v1={compute_signature(payload=body, secret=secret, timestamp=timestamp)}"


class TestWireContract:
    """The SDK must compute what the platform computed, or nothing works."""

    def test_an_empty_object_matches_the_platforms_digest(self) -> None:
        assert (
            compute_signature(payload=b"{}", secret=_SECRET, timestamp=_TIMESTAMP)
            == EXPECTED_EMPTY_OBJECT
        )

    def test_a_real_event_matches_the_platforms_digest(self) -> None:
        assert (
            compute_signature(payload=_BODY, secret=_SECRET, timestamp=_TIMESTAMP) == EXPECTED_EVENT
        )


class TestVerification:
    def test_a_genuine_delivery_verifies(self) -> None:
        event = verify_webhook(
            payload=_BODY, signature_header=_header(), secret=_SECRET, now=_TIMESTAMP
        )
        assert event.type == "run.completed"
        assert event.id == "evt_1"

    def test_a_string_payload_is_accepted(self) -> None:
        # Some frameworks hand back `str`. Encoding it here is safer than
        # letting the caller guess an encoding.
        event = verify_webhook(
            payload=_BODY.decode(), signature_header=_header(), secret=_SECRET, now=_TIMESTAMP
        )
        assert event.type == "run.completed"

    def test_a_forged_signature_is_rejected(self) -> None:
        with pytest.raises(SignatureVerificationError):
            verify_webhook(
                payload=_BODY,
                signature_header=f"t={_TIMESTAMP},v1={'0' * 64}",
                secret=_SECRET,
                now=_TIMESTAMP,
            )

    def test_a_signature_from_a_different_secret_is_rejected(self) -> None:
        with pytest.raises(SignatureVerificationError):
            verify_webhook(
                payload=_BODY,
                signature_header=_header(secret="whsec_someone_elses"),
                secret=_SECRET,
                now=_TIMESTAMP,
            )

    def test_a_tampered_body_is_rejected(self) -> None:
        with pytest.raises(SignatureVerificationError):
            verify_webhook(
                payload=_BODY.replace(b"completed", b"failed!!!"),
                signature_header=_header(),
                secret=_SECRET,
                now=_TIMESTAMP,
            )

    def test_reserializing_the_body_breaks_verification(self) -> None:
        # The most common integration mistake, asserted so the docstring
        # is not the only place it is stated: the signature is over
        # bytes, and a JSON library that spaces its output differently
        # produces a different digest for an identical object.
        reserialized = json.dumps(json.loads(_BODY)).encode()
        assert reserialized != _BODY
        with pytest.raises(SignatureVerificationError):
            verify_webhook(
                payload=reserialized,
                signature_header=_header(),
                secret=_SECRET,
                now=_TIMESTAMP,
            )


class TestReplayWindow:
    def test_a_stale_delivery_is_rejected(self) -> None:
        # Without this, anyone who captures one delivery can resend it
        # indefinitely and it verifies every time.
        with pytest.raises(SignatureVerificationError, match="tolerance"):
            verify_webhook(
                payload=_BODY,
                signature_header=_header(),
                secret=_SECRET,
                now=_TIMESTAMP + DEFAULT_TOLERANCE_SECONDS + 1,
            )

    def test_a_delivery_inside_the_window_is_accepted(self) -> None:
        assert verify_webhook(
            payload=_BODY,
            signature_header=_header(),
            secret=_SECRET,
            now=_TIMESTAMP + DEFAULT_TOLERANCE_SECONDS - 1,
        )

    def test_a_delivery_from_the_future_is_also_rejected(self) -> None:
        # A receiver whose clock runs fast would otherwise accept
        # deliveries stamped ahead of it forever.
        with pytest.raises(SignatureVerificationError, match="tolerance"):
            verify_webhook(
                payload=_BODY,
                signature_header=_header(),
                secret=_SECRET,
                now=_TIMESTAMP - DEFAULT_TOLERANCE_SECONDS - 1,
            )

    def test_the_tolerance_can_be_disabled_deliberately(self) -> None:
        # Zero means "do not check", for replaying a captured delivery
        # against a local server while debugging. Explicit, so it cannot
        # happen by accident.
        assert verify_webhook(
            payload=_BODY,
            signature_header=_header(),
            secret=_SECRET,
            tolerance_seconds=0,
            now=time.time(),
        )

    def test_the_timestamp_is_checked_before_the_digest(self) -> None:
        # A stale delivery should cost nothing to discard, so the cheap
        # check comes first. Asserted through the message, since the
        # ordering is otherwise invisible.
        with pytest.raises(SignatureVerificationError, match="tolerance"):
            verify_webhook(
                payload=_BODY,
                signature_header=f"t={_TIMESTAMP},v1={'0' * 64}",
                secret=_SECRET,
                now=_TIMESTAMP + 10_000,
            )


class TestHeaderParsing:
    def test_a_missing_timestamp_is_rejected(self) -> None:
        with pytest.raises(SignatureVerificationError):
            verify_webhook(
                payload=_BODY, signature_header=f"v1={'0' * 64}", secret=_SECRET, now=_TIMESTAMP
            )

    def test_a_missing_digest_is_rejected(self) -> None:
        with pytest.raises(SignatureVerificationError):
            verify_webhook(
                payload=_BODY, signature_header=f"t={_TIMESTAMP}", secret=_SECRET, now=_TIMESTAMP
            )

    def test_a_non_numeric_timestamp_is_rejected(self) -> None:
        with pytest.raises(SignatureVerificationError):
            verify_webhook(
                payload=_BODY,
                signature_header=f"t=yesterday,v1={'0' * 64}",
                secret=_SECRET,
                now=_TIMESTAMP,
            )

    def test_several_digests_are_all_considered(self) -> None:
        # The header format allows more than one so a secret rotation can
        # be signed under both. A parser reading only the first would
        # reject half the deliveries during exactly the window rotation
        # exists to make safe.
        good = compute_signature(payload=_BODY, secret=_SECRET, timestamp=_TIMESTAMP)
        header = f"t={_TIMESTAMP},v1={'0' * 64},v1={good}"
        assert verify_webhook(
            payload=_BODY, signature_header=header, secret=_SECRET, now=_TIMESTAMP
        )

    def test_an_unknown_version_is_ignored_rather_than_trusted(self) -> None:
        with pytest.raises(SignatureVerificationError):
            verify_webhook(
                payload=_BODY,
                signature_header=f"t={_TIMESTAMP},v99=anything",
                secret=_SECRET,
                now=_TIMESTAMP,
            )


class TestParsedEvent:
    def test_the_envelope_fields_are_exposed(self) -> None:
        body = json.dumps(
            {
                "id": "evt_abc",
                "type": "run.completed",
                "api_version": "v1",
                "created_at": "2026-08-06T12:00:00+00:00",
                "data": {"run_id": "r1"},
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        event = verify_webhook(
            payload=body,
            signature_header=_header(body=body),
            secret=_SECRET,
            now=_TIMESTAMP,
        )
        assert event.id == "evt_abc"
        assert event.api_version == "v1"
        assert event.data == {"run_id": "r1"}

    def test_a_verified_body_that_is_not_json_is_an_error(self) -> None:
        body = b"not json at all"
        with pytest.raises(SignatureVerificationError):
            verify_webhook(
                payload=body,
                signature_header=_header(body=body),
                secret=_SECRET,
                now=_TIMESTAMP,
            )

    def test_a_missing_data_object_becomes_an_empty_dict(self) -> None:
        # A receiver should not have to guard `event.data` for `None` on
        # an event that happens to carry no body.
        body = b'{"id":"evt_1","type":"run.completed"}'
        event = verify_webhook(
            payload=body,
            signature_header=_header(body=body),
            secret=_SECRET,
            now=_TIMESTAMP,
        )
        assert event.data == {}
