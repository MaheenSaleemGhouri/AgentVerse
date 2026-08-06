"""Webhook signing, and when a failed delivery is worth retrying.

The signing tests matter because a signature the customer cannot verify
is indistinguishable, from our side, from an endpoint that is down — the
deliveries fail, the retries exhaust, and nothing in our logs says why.
"""

from __future__ import annotations

import random

import pytest

from agentverse_api.webhook_service.domain.endpoint import (
    FAILURE_THRESHOLD,
    InvalidEventTypeError,
    WebhookEvent,
    next_failure_count,
    parse_events,
    should_disable,
)
from agentverse_api.webhook_service.domain.signing import (
    MAX_ATTEMPTS,
    SIGNATURE_VERSION,
    DeliveryExhaustedError,
    backoff_seconds,
    evaluate_attempt,
    is_success,
    should_retry,
    sign,
    signature_header,
    signing_payload,
    verify,
)

_SECRET = "whsec_0123456789abcdef"
_BODY = '{"id":"evt_1","type":"run.completed"}'

#: The wire contract, pinned. apps/worker signs deliveries with its own
#: copy of this construction (Rule 5 — the two services share no code),
#: and these *identical* literals appear in its
#: `tests/webhooks/test_signing_contract.py`.
#:
#: Known answers rather than a cross-import: importing the sibling
#: package makes the test skip wherever it is not installed, which is
#: each service's own CI job — and a gate that silently skips is worse
#: than no gate. Pinned on both sides, either one drifting fails its own
#: suite.
#:
#: Changing these constants changes the wire format. Every customer's
#: verifier breaks, and that needs a `v2=` alongside `v1=`, not an edit.
_CONTRACT_SECRET = "whsec_deadbeef"
_CONTRACT_TIMESTAMP = 1_800_000_000
EXPECTED_EMPTY_OBJECT = "bdbde3be09b48f018e8bfbaaaceadc664aaee6bbc7a1d2489d33f0f50c9e674c"
EXPECTED_EVENT = "53e42645290d85bfbc1615823cb3bcb7a956c8b7c1ce9d2704a9de4337136e56"
EXPECTED_UNICODE = "6f7eadbd82407a5635d809011b502d05898b9ef878bc43f97a42a4b3e5e5dd69"


class TestWireContract:
    """Pinned against apps/worker. See the note above these constants."""

    def test_an_empty_object_signs_to_the_pinned_digest(self) -> None:
        assert (
            sign(secret=_CONTRACT_SECRET, timestamp=_CONTRACT_TIMESTAMP, body="{}")
            == EXPECTED_EMPTY_OBJECT
        )

    def test_a_real_event_signs_to_the_pinned_digest(self) -> None:
        assert (
            sign(
                secret=_CONTRACT_SECRET,
                timestamp=_CONTRACT_TIMESTAMP,
                body='{"id":"evt_1","type":"run.completed"}',
            )
            == EXPECTED_EVENT
        )

    def test_non_ascii_signs_to_the_pinned_digest(self) -> None:
        # `json.dumps` escapes non-ASCII by default, so the bytes signed
        # are the escaped form. If either side ever passes
        # `ensure_ascii=False`, the digests diverge and every verifier
        # fails on the first accented character a customer sends.
        from agentverse_api.webhook_service.application.webhook_service import serialize_body

        body = serialize_body({"t": "café"})
        assert body == '{"t":"caf\\u00e9"}'
        assert (
            sign(secret=_CONTRACT_SECRET, timestamp=_CONTRACT_TIMESTAMP, body=body)
            == EXPECTED_UNICODE
        )

    def test_the_header_format_is_pinned(self) -> None:
        assert (
            signature_header(secret=_CONTRACT_SECRET, timestamp=_CONTRACT_TIMESTAMP, body="{}")
            == f"t={_CONTRACT_TIMESTAMP},v1={EXPECTED_EMPTY_OBJECT}"
        )

    def test_the_serialized_body_is_pinned(self) -> None:
        from agentverse_api.webhook_service.application.webhook_service import serialize_body

        assert (
            serialize_body({"b": 2, "a": 1, "nested": {"z": 1}}) == '{"a":1,"b":2,"nested":{"z":1}}'
        )

    def test_the_attempt_cap_and_schedule_are_pinned(self) -> None:
        import random

        assert MAX_ATTEMPTS == 6
        bases = [backoff_seconds(attempt=n, jitter=random.Random(0)) for n in range(1, 6)]
        for actual, expected in zip(bases, [10, 60, 300, 900, 3_600], strict=True):
            assert abs(actual - expected) <= expected * 0.2


class TestSigning:
    def test_a_signature_verifies(self) -> None:
        signature = sign(secret=_SECRET, timestamp=1_800_000_000, body=_BODY)
        assert verify(secret=_SECRET, timestamp=1_800_000_000, body=_BODY, provided=signature)

    def test_the_timestamp_is_part_of_what_is_signed(self) -> None:
        # A signature over the body alone is replayable forever: anyone
        # who captures one delivery can resend it indefinitely and it
        # verifies every time.
        first = sign(secret=_SECRET, timestamp=1_800_000_000, body=_BODY)
        second = sign(secret=_SECRET, timestamp=1_800_000_001, body=_BODY)
        assert first != second

    def test_a_changed_body_fails_verification(self) -> None:
        signature = sign(secret=_SECRET, timestamp=1_800_000_000, body=_BODY)
        assert not verify(
            secret=_SECRET,
            timestamp=1_800_000_000,
            body=_BODY.replace("completed", "failed"),
            provided=signature,
        )

    def test_a_different_secret_fails_verification(self) -> None:
        signature = sign(secret=_SECRET, timestamp=1_800_000_000, body=_BODY)
        assert not verify(
            secret="whsec_someone_elses", timestamp=1_800_000_000, body=_BODY, provided=signature
        )

    def test_the_signed_payload_is_timestamp_dot_body(self) -> None:
        # Stated in one place so the sender and the documentation cannot
        # describe two constructions — the failure being that every
        # customer's verifier fails and nobody can tell whose bug it is.
        assert signing_payload(timestamp=17, body="x") == "17.x"

    def test_the_header_carries_the_timestamp_and_a_versioned_digest(self) -> None:
        header = signature_header(secret=_SECRET, timestamp=1_800_000_000, body=_BODY)
        assert header.startswith("t=1800000000,")
        assert f",{SIGNATURE_VERSION}=" in header

    def test_the_version_prefix_leaves_room_for_a_second_scheme(self) -> None:
        # A future construction adds `v2=` alongside `v1=` rather than
        # replacing it, so a customer's verifier keeps working through
        # the transition.
        header = signature_header(secret=_SECRET, timestamp=1, body="x")
        assert header.count("=") >= 2

    def test_verification_is_not_short_circuited_by_a_prefix_match(self) -> None:
        # A verifier returning early on the first differing byte leaks
        # the expected signature to anyone who can measure it.
        signature = sign(secret=_SECRET, timestamp=1, body="x")
        assert not verify(secret=_SECRET, timestamp=1, body="x", provided=signature[:10])


class TestRetryDecisions:
    def test_a_timeout_retries(self) -> None:
        assert should_retry(attempts_made=1, response_status=None) is True

    def test_a_server_error_retries(self) -> None:
        for status in (500, 502, 503, 504):
            assert should_retry(attempts_made=1, response_status=status) is True

    def test_a_client_error_does_not_retry(self) -> None:
        # The endpoint has rejected the request itself. The same bytes
        # will be rejected the same way in an hour, so retrying is noise
        # for both sides.
        for status in (400, 401, 403, 404, 422):
            assert should_retry(attempts_made=1, response_status=status) is False

    def test_a_timeout_status_and_a_rate_limit_do_retry(self) -> None:
        # 408 and 429 are 4xx that mean "not now" rather than "not ever".
        assert should_retry(attempts_made=1, response_status=408) is True
        assert should_retry(attempts_made=1, response_status=429) is True

    def test_retries_stop_at_the_cap(self) -> None:
        # Uncapped retries against an endpoint down for a week are a
        # queue that never drains.
        assert should_retry(attempts_made=MAX_ATTEMPTS, response_status=500) is False

    def test_only_2xx_is_success(self) -> None:
        assert is_success(200) is True
        assert is_success(204) is True
        # A 3xx is not delivery: the drainer does not follow redirects,
        # so treating one as success would mean accepting that the
        # payload went somewhere unverified.
        assert is_success(302) is False
        assert is_success(404) is False


class TestBackoff:
    def test_the_schedule_grows(self) -> None:
        fixed = random.Random(0)
        delays = [backoff_seconds(attempt=n, jitter=fixed) for n in range(1, 6)]
        assert delays == sorted(delays)

    def test_it_is_jittered(self) -> None:
        # Without jitter, every delivery that failed during one outage
        # retries at the same instant when the endpoint recovers — and
        # the platform becomes the thing that knocks it over again.
        samples = {backoff_seconds(attempt=3, jitter=random.Random(seed)) for seed in range(20)}
        assert len(samples) > 1

    def test_jitter_stays_near_the_base(self) -> None:
        for seed in range(50):
            delay = backoff_seconds(attempt=3, jitter=random.Random(seed))
            assert 240 <= delay <= 360  # 300s ± 20%

    def test_a_delay_is_never_zero(self) -> None:
        for seed in range(50):
            assert backoff_seconds(attempt=1, jitter=random.Random(seed)) >= 1

    def test_asking_past_the_schedule_raises(self) -> None:
        with pytest.raises(DeliveryExhaustedError):
            backoff_seconds(attempt=MAX_ATTEMPTS + 5)

    def test_attempt_numbers_are_one_based(self) -> None:
        with pytest.raises(ValueError, match="1-based"):
            backoff_seconds(attempt=0)


class TestAttemptEvaluation:
    def test_a_success_is_delivered_and_not_retried(self) -> None:
        outcome = evaluate_attempt(attempts_made=1, response_status=200, error=None)
        assert outcome.delivered is True
        assert outcome.retry is False

    def test_a_server_error_is_retried(self) -> None:
        outcome = evaluate_attempt(attempts_made=1, response_status=503, error=None)
        assert outcome.delivered is False
        assert outcome.retry is True

    def test_a_client_error_is_final(self) -> None:
        outcome = evaluate_attempt(attempts_made=1, response_status=404, error=None)
        assert outcome.delivered is False
        assert outcome.retry is False

    def test_the_last_attempt_is_final_even_for_a_5xx(self) -> None:
        outcome = evaluate_attempt(attempts_made=MAX_ATTEMPTS, response_status=500, error="boom")
        assert outcome.retry is False


class TestEventSubscriptions:
    def test_known_events_parse(self) -> None:
        assert parse_events(["run.completed", "run.failed"]) == frozenset(
            {WebhookEvent.RUN_COMPLETED, WebhookEvent.RUN_FAILED}
        )

    def test_an_unknown_event_is_refused_with_the_valid_list(self) -> None:
        # A customer subscribing to a typo gets an endpoint that never
        # fires and no indication why.
        with pytest.raises(InvalidEventTypeError) as exc:
            parse_events(["run.complete"])
        assert "run.completed" in str(exc.value)

    def test_every_bad_name_is_reported_at_once(self) -> None:
        with pytest.raises(InvalidEventTypeError) as exc:
            parse_events(["nope", "also-nope"])
        assert set(exc.value.unknown) == {"nope", "also-nope"}

    def test_an_empty_subscription_is_refused_rather_than_meaning_all(self) -> None:
        # A customer who forgot the field would otherwise receive every
        # event the platform emits, including ones added later, at
        # whatever volume they arrive.
        with pytest.raises(InvalidEventTypeError):
            parse_events([])


class TestEndpointHealth:
    def test_a_success_resets_the_failure_count(self) -> None:
        # Reset rather than decay: an endpoint that answered is working
        # now, and carrying old failures forward would eventually disable
        # a healthy URL that had a bad week months ago.
        assert next_failure_count(current=19, delivered=True) == 0

    def test_a_failure_increments(self) -> None:
        assert next_failure_count(current=3, delivered=False) == 4

    def test_an_endpoint_is_disabled_at_the_threshold(self) -> None:
        assert should_disable(FAILURE_THRESHOLD) is True
        assert should_disable(FAILURE_THRESHOLD - 1) is False
