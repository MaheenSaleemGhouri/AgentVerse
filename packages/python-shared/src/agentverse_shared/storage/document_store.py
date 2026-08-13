"""Uploaded knowledge-base document storage.

Shared because apps/api writes on upload and apps/worker reads during
ingestion — they must agree on the key layout exactly, and a divergence
would surface as "file not found" for every upload rather than at build
time.

Security posture (`secure-coding-expert`, CLAUDE.md §10):
- The stored name is **generated**, never the client-supplied filename —
  no path traversal, no collisions, no executable-looking names.
- Keys are workspace-prefixed, so a listing/enumeration bug cannot cross
  tenants and on-disk layout mirrors the tenancy model.
- Resolved paths/keys are verified against `_KEY_PATTERN` before any
  filesystem or network call, so a crafted key cannot escape the
  configured root (local) or address an unrelated object (S3).
- The root is expected to be outside any web-served directory; nothing
  here serves files over HTTP.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import boto3
from botocore.config import Config as BotoConfig

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class DocumentStoreError(Exception):
    pass


class DocumentNotFoundError(DocumentStoreError):
    pass


#: A storage key is exactly `<workspace_uuid>/<document_uuid><ext>`.
#: Validated on the way in *and* on the way out, because the read path
#: takes keys from the database, which a future bug could poison.
_KEY_PATTERN = re.compile(r"^[0-9a-fA-F-]{36}/[0-9a-fA-F-]{36}(?:\.[A-Za-z0-9]{1,12})?$")

#: Extensions we preserve on the generated name purely so operators can
#: eyeball a storage directory. Anything else is stored extension-less —
#: the extension is cosmetic and never used to decide how to parse a file.
_SAFE_EXTENSIONS = {
    "pdf",
    "docx",
    "doc",
    "txt",
    "md",
    "markdown",
    "mdx",
    "csv",
    "tsv",
    "json",
    "jsonl",
    "ndjson",
    "rtf",
}


def _validate_key(key: str) -> None:
    if not _KEY_PATTERN.match(key):
        raise DocumentStoreError(f"malformed storage key: {key!r}")


def build_storage_key(*, workspace_id: str, original_filename: str) -> str:
    """Generates the storage key for a new upload.

    The client's filename influences only the (cosmetic, allowlisted)
    extension — never the directory or basename.
    """
    suffix = ""
    if "." in original_filename:
        candidate = original_filename.rsplit(".", 1)[-1].lower()
        if candidate in _SAFE_EXTENSIONS:
            suffix = f".{candidate}"
    return f"{workspace_id}/{uuid.uuid4()}{suffix}"


class DocumentStore(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...


class LocalDocumentStore:
    """Filesystem-backed store for local dev and single-node deploys.

    Object storage (S3/R2) is the production escalation and implements the
    same Protocol — deferred until a deployment actually needs it rather
    than abstracted speculatively (CLAUDE.md §16).
    """

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root).resolve()

    # Filesystem calls are synchronous and a knowledge-base document is
    # megabytes, not bytes — running them inline would stall the event
    # loop for every other request on the process (CLAUDE.md Rule 12).
    # `to_thread` is the explicit offload that rule requires.

    async def put(self, key: str, data: bytes) -> None:
        path = self._resolve(key)
        await asyncio.to_thread(self._write, path, data)

    async def get(self, key: str) -> bytes:
        path = self._resolve(key)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError as exc:
            raise DocumentNotFoundError(f"no stored document for key {key}") from exc

    async def delete(self, key: str) -> None:
        # Missing is not an error: delete must be safe to retry, since the
        # queue delivers at least once.
        await asyncio.to_thread(self._resolve(key).unlink, True)

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def _resolve(self, key: str) -> Path:
        _validate_key(key)

        path = (self._root / key).resolve()
        # Defense in depth behind the pattern check: even a key that
        # satisfied the regex must provably land inside the root.
        if not path.is_relative_to(self._root):
            raise DocumentStoreError(f"storage key escapes the root: {key!r}")
        return path


class S3DocumentStore:
    """S3-compatible store for uploaded knowledge-base documents.

    The production escalation `LocalDocumentStore`'s docstring names:
    apps/api and apps/worker run as separate containers with no shared
    filesystem, so a local root written by one is invisible to the
    other — every upload "succeeded" but every ingestion job then failed
    with a not-found. Object storage removes the shared-filesystem
    assumption entirely; either service reaches the same bucket over
    the network.

    Works against any S3-compatible endpoint (Neon Object Storage, AWS
    S3, Cloudflare R2, ...) — `endpoint_url` plus path-style addressing
    is the only thing that varies between them.
    """

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        self._bucket = bucket
        self._client: S3Client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            # Required by Neon Object Storage (and several other
            # S3-compatible providers); virtual-hosted-style addressing
            # would resolve the bucket into the hostname, which these
            # endpoints don't route.
            config=BotoConfig(s3={"addressing_style": "path"}),
        )

    # boto3 is synchronous; offloaded via `to_thread` for the same reason
    # `LocalDocumentStore` offloads filesystem calls (CLAUDE.md Rule 12).

    async def put(self, key: str, data: bytes) -> None:
        _validate_key(key)
        await asyncio.to_thread(
            self._client.put_object, Bucket=self._bucket, Key=key, Body=data
        )

    async def get(self, key: str) -> bytes:
        _validate_key(key)
        return await asyncio.to_thread(self._get_sync, key)

    async def delete(self, key: str) -> None:
        _validate_key(key)
        # Missing is not an error: delete must be safe to retry, since the
        # queue delivers at least once — matches LocalDocumentStore.
        await asyncio.to_thread(self._delete_sync, key)

    def _get_sync(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except self._client.exceptions.NoSuchKey as exc:
            raise DocumentNotFoundError(f"no stored document for key {key}") from exc
        body: bytes = response["Body"].read()
        return body

    def _delete_sync(self, key: str) -> None:
        with contextlib.suppress(self._client.exceptions.NoSuchKey):
            self._client.delete_object(Bucket=self._bucket, Key=key)


def build_document_store(
    *,
    root: str,
    bucket: str | None,
    endpoint_url: str | None,
    region: str | None,
    access_key_id: str | None,
    secret_access_key: str | None,
) -> DocumentStore:
    """The one place that decides `S3DocumentStore` vs `LocalDocumentStore`.

    apps/api and apps/worker each call this from their own composition
    root with their own (identically-shaped) settings, so the choice
    logic exists exactly once rather than being reimplemented — and
    silently able to drift — on both sides of the contract.
    """
    if bucket and endpoint_url and region and access_key_id and secret_access_key:
        return S3DocumentStore(
            bucket=bucket,
            endpoint_url=endpoint_url,
            region=region,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
        )
    return LocalDocumentStore(root)
