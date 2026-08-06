"""The signing construction, worker side.

A deliberate copy of `apps/api`'s
`webhook_service.domain.signing` — the two services share no code
(Rule 5), and this is the same "shared wire contract, duplicated with a
test guarding it" pattern `mcp/tables.py` already uses. The guard is
`tests/webhooks/test_signing_contract.py`, which asserts byte-for-byte
agreement with the API's implementation; if either side changes, that
test fails rather than every customer's verifier failing silently.

`serialize_body` matters more than it looks: the signature covers the
body, so signing a differently-serialized string than the one
transmitted produces a signature that fails at every customer, and the
bug is invisible from our side.
"""

from __future__ import annotations

import hashlib
import hmac
import json

SIGNATURE_VERSION = "v1"


def signing_payload(*, timestamp: int, body: str) -> str:
    return f"{timestamp}.{body}"


def sign(*, secret: str, timestamp: int, body: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        signing_payload(timestamp=timestamp, body=body).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def signature_header(*, secret: str, timestamp: int, body: str) -> str:
    return (
        f"t={timestamp},{SIGNATURE_VERSION}={sign(secret=secret, timestamp=timestamp, body=body)}"
    )


def serialize_body(envelope: dict[str, object]) -> str:
    """The exact bytes signed and sent.

    `sort_keys` and no spaces, so the string is byte-stable across
    processes and Python versions — the signature is over these bytes,
    and a re-serialization that differs by one space fails verification.
    """
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"), default=str)
