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
- Resolved paths are verified to stay inside the configured root, so a
  crafted key cannot escape it even if a caller passes one through.
- The root is expected to be outside any web-served directory; nothing
  here serves files over HTTP.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path
from typing import Protocol


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
        if not _KEY_PATTERN.match(key):
            raise DocumentStoreError(f"malformed storage key: {key!r}")

        path = (self._root / key).resolve()
        # Defense in depth behind the pattern check: even a key that
        # satisfied the regex must provably land inside the root.
        if not path.is_relative_to(self._root):
            raise DocumentStoreError(f"storage key escapes the root: {key!r}")
        return path
