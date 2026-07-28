"""Tests for envelope encryption of third-party credentials.

The properties worth asserting are the ones that hold under attack, not
that encrypt-then-decrypt round-trips: that a Postgres dump is useless
without the KEK, that ciphertext moved between rows fails, that tampering
is detected, and that a missing key fails loudly instead of silently
storing plaintext.
"""

from __future__ import annotations

import base64
import os

import pytest

from agentverse_shared.security.envelope import (
    CredentialCryptoError,
    CredentialVault,
    KeyRing,
    MissingKeyError,
    credential_aad,
    hint_for,
)

SECRET = "ghp_averyrealisticlookinggithubtoken0000"


def _ring(versions: tuple[str, ...] = ("v1",), active: str = "v1") -> KeyRing:
    return KeyRing({version: os.urandom(32) for version in versions}, active)


@pytest.fixture
def vault() -> CredentialVault:
    return CredentialVault(_ring())


class TestRoundTrip:
    def test_seals_and_opens(self, vault: CredentialVault) -> None:
        assert vault.open(vault.seal(SECRET)) == SECRET

    def test_ciphertext_does_not_contain_the_plaintext(self, vault: CredentialVault) -> None:
        """The whole point: a database dump is the realistic breach."""
        sealed = vault.seal(SECRET)
        assert SECRET.encode() not in sealed.ciphertext
        assert SECRET.encode() not in sealed.wrapped_dek

    def test_the_same_secret_seals_differently_each_time(self, vault: CredentialVault) -> None:
        """A fresh DEK per credential means identical secrets do not
        produce identical ciphertext — otherwise an attacker with dump
        access could tell which workspaces share a key."""
        assert vault.seal(SECRET).ciphertext != vault.seal(SECRET).ciphertext

    def test_records_the_key_version_that_wrapped_it(self, vault: CredentialVault) -> None:
        assert vault.seal(SECRET).key_version == "v1"

    def test_handles_unicode_secrets(self, vault: CredentialVault) -> None:
        secret = "pässwörd-🔑-値"
        assert vault.open(vault.seal(secret)) == secret


class TestTamperDetection:
    def test_a_modified_ciphertext_fails(self, vault: CredentialVault) -> None:
        """AES-GCM is authenticated — a tampered ciphertext fails rather
        than decrypting to garbage that gets sent to a third party."""
        sealed = vault.seal(SECRET)
        corrupted = bytearray(sealed.ciphertext)
        corrupted[-1] ^= 0x01
        with pytest.raises(CredentialCryptoError):
            vault.open(type(sealed)(bytes(corrupted), sealed.wrapped_dek, sealed.key_version))

    def test_a_modified_wrapped_key_fails(self, vault: CredentialVault) -> None:
        sealed = vault.seal(SECRET)
        corrupted = bytearray(sealed.wrapped_dek)
        corrupted[-1] ^= 0x01
        with pytest.raises(CredentialCryptoError):
            vault.open(type(sealed)(sealed.ciphertext, bytes(corrupted), sealed.key_version))

    def test_the_error_does_not_say_why(self, vault: CredentialVault) -> None:
        """ "Wrong key" versus "tampered" is something an attacker probing
        the vault would like to learn."""
        sealed = vault.seal(SECRET)
        corrupted = bytearray(sealed.ciphertext)
        corrupted[0] ^= 0xFF
        with pytest.raises(CredentialCryptoError) as caught:
            vault.open(type(sealed)(bytes(corrupted), sealed.wrapped_dek, sealed.key_version))
        assert "tamper" not in str(caught.value).lower()
        assert "key" not in str(caught.value).lower()


class TestAssociatedData:
    def test_ciphertext_moved_to_another_row_fails_to_open(self, vault: CredentialVault) -> None:
        """Without binding, a ciphertext copied from workspace A's row
        into workspace B's row would decrypt cleanly and hand B a working
        credential belonging to A."""
        aad_a = credential_aad(workspace_id="ws-a", installed_server_id="srv-1", key="TOKEN")
        aad_b = credential_aad(workspace_id="ws-b", installed_server_id="srv-1", key="TOKEN")
        sealed = vault.seal(SECRET, associated_data=aad_a)
        with pytest.raises(CredentialCryptoError):
            vault.open(sealed, associated_data=aad_b)

    def test_the_same_binding_opens(self, vault: CredentialVault) -> None:
        aad = credential_aad(workspace_id="ws-a", installed_server_id="srv-1", key="TOKEN")
        assert vault.open(vault.seal(SECRET, associated_data=aad), associated_data=aad) == SECRET

    def test_binding_distinguishes_credential_keys_on_one_server(
        self, vault: CredentialVault
    ) -> None:
        aad_token = credential_aad(workspace_id="w", installed_server_id="s", key="TOKEN")
        aad_secret = credential_aad(workspace_id="w", installed_server_id="s", key="SECRET")
        sealed = vault.seal(SECRET, associated_data=aad_token)
        with pytest.raises(CredentialCryptoError):
            vault.open(sealed, associated_data=aad_secret)


class TestKeyRotation:
    def test_rewrap_moves_a_secret_to_the_active_key(self) -> None:
        ring = _ring(("v1", "v2"), active="v1")
        old = CredentialVault(ring)
        sealed = old.seal(SECRET)

        rotated = CredentialVault(KeyRing(dict(ring._keys), "v2"))  # noqa: SLF001 - test fixture
        rewrapped = rotated.rewrap(sealed)

        assert rewrapped.key_version == "v2"
        assert rotated.open(rewrapped) == SECRET

    def test_rewrap_does_not_touch_the_ciphertext(self) -> None:
        """This is what makes rotation cheap: the secret itself is never
        decrypted, so a rotation sweep does not put every plaintext
        credential through memory."""
        ring = _ring(("v1", "v2"), active="v1")
        sealed = CredentialVault(ring).seal(SECRET)
        rewrapped = CredentialVault(KeyRing(dict(ring._keys), "v2")).rewrap(sealed)  # noqa: SLF001
        assert rewrapped.ciphertext == sealed.ciphertext

    def test_a_secret_under_a_retired_key_is_still_readable(self) -> None:
        """Old rows stay readable under the old KEK until a background
        rewrap moves them — otherwise rotation is a hard cutover."""
        ring = _ring(("v1", "v2"), active="v1")
        sealed = CredentialVault(ring).seal(SECRET)
        assert CredentialVault(KeyRing(dict(ring._keys), "v2")).open(sealed) == SECRET  # noqa: SLF001

    def test_a_secret_under_an_unknown_key_fails_loudly(self, vault: CredentialVault) -> None:
        sealed = vault.seal(SECRET)
        with pytest.raises(MissingKeyError):
            vault.open(type(sealed)(sealed.ciphertext, sealed.wrapped_dek, "v99"))


class TestKeyRing:
    def test_from_env_reads_versioned_keys(self) -> None:
        key = base64.b64encode(os.urandom(32)).decode()
        ring = KeyRing.from_env({"AGENTVERSE_CREDENTIAL_KEK_V1": key}, active_version="v1")
        assert ring.active_version == "v1"

    def test_missing_active_key_fails_at_construction(self) -> None:
        """A vault that starts successfully and then cannot decrypt
        anything looks healthy while every tool call fails."""
        with pytest.raises(MissingKeyError, match="AGENTVERSE_CREDENTIAL_KEK_V1"):
            KeyRing.from_env({}, active_version="v1")

    def test_there_is_no_development_fallback_key(self) -> None:
        """A hardcoded default is indistinguishable from no encryption,
        and would ship (CLAUDE.md Rule 1)."""
        with pytest.raises(MissingKeyError):
            KeyRing.from_env({"UNRELATED": "x"}, active_version="v1")

    def test_a_wrong_length_key_is_rejected(self) -> None:
        short = base64.b64encode(os.urandom(16)).decode()
        with pytest.raises(MissingKeyError, match="AES-256"):
            KeyRing.from_env({"AGENTVERSE_CREDENTIAL_KEK_V1": short}, active_version="v1")

    def test_malformed_base64_is_rejected(self) -> None:
        with pytest.raises(MissingKeyError, match="base64"):
            KeyRing.from_env(
                {"AGENTVERSE_CREDENTIAL_KEK_V1": "!!!not base64!!!"}, active_version="v1"
            )

    def test_generated_keys_are_the_right_size(self) -> None:
        assert len(base64.b64decode(KeyRing.generate_key_b64())) == 32


class TestHint:
    def test_is_the_tail_not_the_prefix(self) -> None:
        """Many credential formats put a recognisable low-entropy prefix
        at the front (`sk-`, `ghp_`, `xoxb-`). A prefix identifies the
        kind of key and its issuer; the tail only answers "is this the
        one I pasted?"."""
        hint = hint_for(SECRET)
        assert hint == SECRET[-4:]
        assert not SECRET.startswith(hint)

    def test_short_secrets_get_no_hint(self) -> None:
        assert hint_for("short") == ""

    def test_reveals_at_most_four_characters(self) -> None:
        assert len(hint_for(SECRET)) == 4
