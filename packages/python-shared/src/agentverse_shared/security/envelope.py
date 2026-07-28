"""Envelope encryption for third-party credentials.

Two layers, deliberately:

1. A fresh **data encryption key (DEK)** per credential encrypts the
   secret with AES-256-GCM.
2. A **key-encryption key (KEK)** from the runtime environment encrypts
   the DEK.

Postgres stores only ciphertext and the wrapped DEK. A database dump —
the realistic breach — yields nothing usable without the KEK, which lives
in the secrets manager and never in the database.

Per-credential DEKs are not ceremony. They mean rotating the KEK rewraps
a small key rather than re-encrypting every secret, and a single
compromised DEK exposes exactly one credential.

**No custom crypto.** AES-GCM from `cryptography`, which is authenticated
— a tampered ciphertext fails to decrypt rather than decrypting to
garbage. Nothing here invents a construction (CLAUDE.md §10).
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

#: AES-256.
_KEY_BYTES = 32
#: 96 bits, the size AES-GCM is specified for. A random nonce of this
#: length is safe because every encryption uses a *fresh* key, so the
#: (key, nonce) pair cannot repeat — which is the failure GCM cares about.
_NONCE_BYTES = 12


class CredentialCryptoError(Exception):
    """Encryption or decryption failed.

    Deliberately carries no detail about *why*. A caller learning
    "wrong key" versus "tampered ciphertext" learns something an attacker
    probing the vault would also like to know.
    """


class MissingKeyError(CredentialCryptoError):
    """The configured KEK version has no key.

    Raised loudly at resolution time rather than falling back to a
    default. `os.environ.get("KEY", "changeme")` is prohibited
    (CLAUDE.md Rule 1), and silently skipping encryption would be worse
    than failing.
    """


@dataclass(frozen=True, slots=True)
class SealedSecret:
    """What gets stored. Never contains plaintext.

    `key_version` records which KEK wrapped this DEK, so rotating the root
    key does not require re-encrypting every row at once — old rows stay
    readable under the old KEK until a background rewrap moves them.
    """

    ciphertext: bytes
    wrapped_dek: bytes
    key_version: str


class KeyRing:
    """Resolves KEKs by version.

    Keys come from the environment as base64, named
    `AGENTVERSE_CREDENTIAL_KEK_<VERSION>`. Loaded once at construction
    rather than read per call, so a key rotation is a deploy, not a
    surprise mid-request.

    A missing or malformed key fails at construction. A vault that starts
    successfully and then cannot decrypt anything is the worst outcome —
    it looks healthy while every tool call fails.
    """

    ENV_PREFIX = "AGENTVERSE_CREDENTIAL_KEK_"

    def __init__(self, keys: dict[str, bytes], active_version: str) -> None:
        if active_version not in keys:
            raise MissingKeyError(f"active key version {active_version!r} is not in the key ring")
        for version, key in keys.items():
            if len(key) != _KEY_BYTES:
                raise MissingKeyError(
                    f"key version {version!r} is {len(key)} bytes; AES-256 needs {_KEY_BYTES}"
                )
        self._keys = dict(keys)
        self._active_version = active_version

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, *, active_version: str = "v1") -> KeyRing:
        """Builds a ring from `AGENTVERSE_CREDENTIAL_KEK_*` variables.

        Fails loudly when the active version is absent. There is
        deliberately no development fallback: a hardcoded default key is
        indistinguishable from no encryption, and would ship.
        """
        source = env if env is not None else dict(os.environ)
        keys: dict[str, bytes] = {}
        for name, value in source.items():
            if not name.startswith(cls.ENV_PREFIX):
                continue
            version = name[len(cls.ENV_PREFIX) :].lower()
            try:
                keys[version] = base64.b64decode(value, validate=True)
            except Exception as exc:  # noqa: BLE001 - re-raised with context, value never logged
                raise MissingKeyError(f"key version {version!r} is not valid base64") from exc
        if active_version not in keys:
            raise MissingKeyError(
                f"{cls.ENV_PREFIX}{active_version.upper()} is not set. Credentials cannot be "
                "encrypted without it, and starting without encryption is not an option."
            )
        return cls(keys, active_version)

    @property
    def active_version(self) -> str:
        return self._active_version

    def key_for(self, version: str) -> bytes:
        key = self._keys.get(version)
        if key is None:
            raise MissingKeyError(
                f"no key for version {version!r}; a credential encrypted under it cannot be read"
            )
        return key

    @staticmethod
    def generate_key_b64() -> str:
        """A fresh KEK, base64-encoded, for operators setting one up.

        Here rather than in a script so the key size is defined in exactly
        one place as the code that validates it.
        """
        return base64.b64encode(os.urandom(_KEY_BYTES)).decode()


class CredentialVault:
    """Seals and opens credentials.

    Stateless apart from the key ring, and takes no `workspace_id` —
    tenant scoping belongs to the repository query that fetches the row,
    not here. Putting it in both places would suggest this class enforces
    something it does not.
    """

    def __init__(self, key_ring: KeyRing) -> None:
        self._ring = key_ring

    def seal(self, plaintext: str, *, associated_data: bytes | None = None) -> SealedSecret:
        """Encrypts under a fresh DEK, wrapped by the active KEK.

        `associated_data` is authenticated but not encrypted — pass the
        credential's identity (workspace + server + key) so ciphertext
        moved to a different row fails to decrypt rather than silently
        becoming another credential's value.
        """
        dek = os.urandom(_KEY_BYTES)
        data_nonce = os.urandom(_NONCE_BYTES)
        ciphertext = data_nonce + AESGCM(dek).encrypt(
            data_nonce, plaintext.encode("utf-8"), associated_data
        )

        kek_nonce = os.urandom(_NONCE_BYTES)
        wrapped = kek_nonce + AESGCM(self._ring.key_for(self._ring.active_version)).encrypt(
            kek_nonce, dek, associated_data
        )
        return SealedSecret(
            ciphertext=ciphertext, wrapped_dek=wrapped, key_version=self._ring.active_version
        )

    def open(self, sealed: SealedSecret, *, associated_data: bytes | None = None) -> str:
        """Decrypts. Raises rather than returning a partial or empty value.

        A vault that returned `""` on failure would send an empty
        credential to a third party, which reads as an auth failure rather
        than as the decryption bug it is.
        """
        try:
            kek = self._ring.key_for(sealed.key_version)
            dek = AESGCM(kek).decrypt(
                sealed.wrapped_dek[:_NONCE_BYTES],
                sealed.wrapped_dek[_NONCE_BYTES:],
                associated_data,
            )
            plaintext = AESGCM(dek).decrypt(
                sealed.ciphertext[:_NONCE_BYTES],
                sealed.ciphertext[_NONCE_BYTES:],
                associated_data,
            )
        except MissingKeyError:
            raise
        except (InvalidTag, ValueError, IndexError) as exc:
            # Detail deliberately dropped — see CredentialCryptoError.
            raise CredentialCryptoError("credential could not be decrypted") from exc
        return plaintext.decode("utf-8")

    def rewrap(self, sealed: SealedSecret, *, associated_data: bytes | None = None) -> SealedSecret:
        """Re-wraps a DEK under the active KEK without touching the
        ciphertext.

        This is what makes KEK rotation cheap: the secret itself is never
        decrypted-and-re-encrypted, so a rotation sweep does not put every
        plaintext credential through memory.
        """
        kek = self._ring.key_for(sealed.key_version)
        try:
            dek = AESGCM(kek).decrypt(
                sealed.wrapped_dek[:_NONCE_BYTES],
                sealed.wrapped_dek[_NONCE_BYTES:],
                associated_data,
            )
        except (InvalidTag, ValueError, IndexError) as exc:
            raise CredentialCryptoError("wrapped key could not be unwrapped") from exc

        nonce = os.urandom(_NONCE_BYTES)
        wrapped = nonce + AESGCM(self._ring.key_for(self._ring.active_version)).encrypt(
            nonce, dek, associated_data
        )
        return SealedSecret(
            ciphertext=sealed.ciphertext,
            wrapped_dek=wrapped,
            key_version=self._ring.active_version,
        )


def credential_aad(*, workspace_id: str, installed_server_id: str, key: str) -> bytes:
    """Binds ciphertext to the row it belongs to.

    Without this, a ciphertext copied from workspace A's row into
    workspace B's row would decrypt cleanly and hand B a working
    credential belonging to A. With it, the copy fails to authenticate.
    """
    return f"{workspace_id}|{installed_server_id}|{key}".encode()


def hint_for(plaintext: str) -> str:
    """The only part of a secret ever shown back.

    Last four characters, never a prefix: many credential formats put a
    recognisable, low-entropy prefix at the front (`sk-`, `ghp_`, `xoxb-`),
    so a prefix identifies the *kind* of key and its issuer while the tail
    only answers "is this the one I pasted?". Short secrets get nothing.
    """
    return plaintext[-4:] if len(plaintext) >= 8 else ""
