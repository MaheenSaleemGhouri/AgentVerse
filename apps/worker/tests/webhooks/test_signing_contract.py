"""The signing construction, pinned to fixed expected values.

`webhooks/signing.py` is a deliberate copy of apps/api's
`webhook_service.domain.signing` — the two services share no code
(Rule 5), the same "shared wire contract, duplicated with a test
guarding it" pattern `mcp/tables.py` uses. This file is that guard, and
it is what makes the duplication acceptable rather than merely
tolerated: without it, a change to either side produces signatures every
customer's verifier rejects, the deliveries fail, the retries exhaust,
and nothing in our logs distinguishes that from every endpoint going
down at once.

**Known-answer, not cross-import.** The obvious version of this test
imports apps/api and compares — and then skips in every environment
where the sibling package is not installed, which is the worker's own
test run. A gate that silently skips is worse than no gate, so the
expected digests are literals here and the *identical* literals appear
in apps/api's `test_signing_and_retries.py`. Either side drifting fails
its own suite, in its own CI job, with no install coupling between them.

If you are changing these constants, you are changing the wire format:
every customer's verifier breaks, and that needs a `v2=` alongside `v1=`
rather than an edit here.
"""

from __future__ import annotations

import pytest

from agentverse_worker.webhooks import drainer, signing

_SECRET = "whsec_deadbeef"
_TIMESTAMP = 1_800_000_000

#: Fixed by contract. Identical literals live in apps/api's test suite.
EXPECTED_EMPTY_OBJECT = "bdbde3be09b48f018e8bfbaaaceadc664aaee6bbc7a1d2489d33f0f50c9e674c"
EXPECTED_EVENT = "53e42645290d85bfbc1615823cb3bcb7a956c8b7c1ce9d2704a9de4337136e56"
EXPECTED_UNICODE = "6f7eadbd82407a5635d809011b502d05898b9ef878bc43f97a42a4b3e5e5dd69"


class TestKnownAnswers:
    def test_an_empty_object_signs_to_the_pinned_digest(self) -> None:
        assert (
            signing.sign(secret=_SECRET, timestamp=_TIMESTAMP, body="{}") == EXPECTED_EMPTY_OBJECT
        )

    def test_a_real_event_signs_to_the_pinned_digest(self) -> None:
        body = '{"id":"evt_1","type":"run.completed"}'
        assert signing.sign(secret=_SECRET, timestamp=_TIMESTAMP, body=body) == EXPECTED_EVENT

    def test_non_ascii_survives_the_round_trip(self) -> None:
        # `json.dumps` escapes non-ASCII by default, so the bytes signed
        # are the escaped form. If either side ever passes
        # `ensure_ascii=False` the digests diverge and every verifier
        # fails on the first accented character a customer sends.
        body = signing.serialize_body({"t": "café"})
        assert body == '{"t":"caf\\u00e9"}'
        assert signing.sign(secret=_SECRET, timestamp=_TIMESTAMP, body=body) == EXPECTED_UNICODE

    def test_the_header_format_is_pinned(self) -> None:
        assert signing.signature_header(secret=_SECRET, timestamp=_TIMESTAMP, body="{}") == (
            f"t={_TIMESTAMP},v1={EXPECTED_EMPTY_OBJECT}"
        )

    def test_the_version_label_is_pinned(self) -> None:
        assert signing.SIGNATURE_VERSION == "v1"


class TestSerialization:
    def test_the_body_is_byte_stable_and_pinned(self) -> None:
        # The signature covers these bytes. A re-serialization differing
        # by one space produces a signature that fails at every customer.
        assert signing.serialize_body({"b": 2, "a": 1, "nested": {"z": 1}}) == (
            '{"a":1,"b":2,"nested":{"z":1}}'
        )

    def test_key_order_does_not_affect_the_bytes(self) -> None:
        assert signing.serialize_body({"b": 1, "a": 2}) == signing.serialize_body({"a": 2, "b": 1})

    def test_an_empty_envelope_serializes(self) -> None:
        assert signing.serialize_body({}) == "{}"


class TestRetryPolicy:
    def test_the_attempt_cap_is_pinned(self) -> None:
        # Diverging from apps/api here means the queue and the customer
        # disagree about whether a delivery is still coming.
        assert drainer.MAX_ATTEMPTS == 6

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (None, True),  # timeout — no answer at all
            (500, True),
            (503, True),
            (408, True),  # 4xx that means "not now"
            (429, True),
            (400, False),  # the request itself is wrong; retrying is noise
            (404, False),
            (422, False),
        ],
    )
    def test_the_retry_decision_is_pinned(self, status: int | None, expected: bool) -> None:
        assert drainer.should_retry(attempts_made=1, response_status=status) is expected

    def test_retries_stop_at_the_cap(self) -> None:
        assert (
            drainer.should_retry(attempts_made=drainer.MAX_ATTEMPTS, response_status=500) is False
        )

    def test_the_backoff_schedule_is_pinned(self) -> None:
        assert [drainer.backoff_seconds(n) for n in range(1, 6)] == [10, 60, 300, 900, 3_600]

    def test_the_schedule_saturates_rather_than_indexing_past_its_end(self) -> None:
        assert drainer.backoff_seconds(99) == 3_600
