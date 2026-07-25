"""Unit tests for JWT verification (ADR-0005) — no real network call to a
JWKS endpoint: `PyJWKClient.get_signing_key_from_jwt` is monkeypatched to
return a real Ed25519 keypair generated in-test, so the actual signature
verification, issuer/audience, and expiry logic is exercised for real.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agentverse_api.auth_service.infrastructure.jwt_verifier import (
    InvalidIdentityTokenError,
    JwtVerifier,
)

ISSUER = "http://web:3000"
AUDIENCE = "http://web:3000"


@pytest.fixture
def keypair() -> tuple[Ed25519PrivateKey, object]:
    private_key = Ed25519PrivateKey.generate()
    return private_key, private_key.public_key()


@pytest.fixture
def verifier(
    keypair: tuple[Ed25519PrivateKey, object], monkeypatch: pytest.MonkeyPatch
) -> Iterator[JwtVerifier]:
    _private_key, public_key = keypair
    instance = JwtVerifier(
        jwks_url="http://web:3000/api/auth/jwks", issuer=ISSUER, audience=AUDIENCE
    )
    monkeypatch.setattr(
        instance._jwks_client,  # noqa: SLF001 - test needs to stub the network-calling internal
        "get_signing_key_from_jwt",
        lambda _token: SimpleNamespace(key=public_key),
    )
    yield instance


def _sign(private_key: Ed25519PrivateKey, **claim_overrides: object) -> str:
    now = int(time.time())
    claims = {
        "sub": "user-123",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 900,
        **claim_overrides,
    }
    return jwt.encode(claims, private_key, algorithm="EdDSA")


def test_verify_valid_token_returns_subject(
    keypair: tuple[Ed25519PrivateKey, object], verifier: JwtVerifier
) -> None:
    private_key, _public_key = keypair
    token = _sign(private_key)

    assert verifier.verify_and_get_user_id(token) == "user-123"


def test_verify_rejects_expired_token(
    keypair: tuple[Ed25519PrivateKey, object], verifier: JwtVerifier
) -> None:
    private_key, _public_key = keypair
    expired = _sign(private_key, iat=int(time.time()) - 1000, exp=int(time.time()) - 100)

    with pytest.raises(InvalidIdentityTokenError):
        verifier.verify_and_get_user_id(expired)


def test_verify_rejects_wrong_audience(
    keypair: tuple[Ed25519PrivateKey, object], verifier: JwtVerifier
) -> None:
    private_key, _public_key = keypair
    token = _sign(private_key, aud="http://attacker.example")

    with pytest.raises(InvalidIdentityTokenError):
        verifier.verify_and_get_user_id(token)


def test_verify_rejects_wrong_issuer(
    keypair: tuple[Ed25519PrivateKey, object], verifier: JwtVerifier
) -> None:
    private_key, _public_key = keypair
    token = _sign(private_key, iss="http://attacker.example")

    with pytest.raises(InvalidIdentityTokenError):
        verifier.verify_and_get_user_id(token)


def test_verify_rejects_token_signed_by_a_different_key(verifier: JwtVerifier) -> None:
    other_key = Ed25519PrivateKey.generate()
    token = _sign(other_key)

    with pytest.raises(InvalidIdentityTokenError):
        verifier.verify_and_get_user_id(token)


def test_verify_rejects_token_with_no_subject(
    keypair: tuple[Ed25519PrivateKey, object], verifier: JwtVerifier
) -> None:
    private_key, _public_key = keypair
    now = int(time.time())
    token = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 900},
        private_key,
        algorithm="EdDSA",
    )

    with pytest.raises(InvalidIdentityTokenError):
        verifier.verify_and_get_user_id(token)
