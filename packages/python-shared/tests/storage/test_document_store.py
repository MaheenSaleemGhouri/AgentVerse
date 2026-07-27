from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from agentverse_shared.storage.document_store import (
    DocumentNotFoundError,
    DocumentStoreError,
    LocalDocumentStore,
    build_storage_key,
)

WS = str(uuid.uuid4())


# --- key generation -----------------------------------------------------


def test_key_is_workspace_prefixed() -> None:
    # Tenancy is visible in the on-disk layout, so an enumeration bug
    # cannot cross workspaces.
    key = build_storage_key(workspace_id=WS, original_filename="report.pdf")

    assert key.startswith(f"{WS}/")


def test_key_never_contains_the_client_filename() -> None:
    key = build_storage_key(workspace_id=WS, original_filename="payroll-secrets.pdf")

    assert "payroll" not in key
    assert "secrets" not in key


def test_key_preserves_only_an_allowlisted_extension() -> None:
    assert build_storage_key(workspace_id=WS, original_filename="a.pdf").endswith(".pdf")
    # Not on the allowlist — stored extension-less rather than as .exe.
    assert not build_storage_key(workspace_id=WS, original_filename="a.exe").endswith(".exe")


def test_keys_are_unique_for_identical_filenames() -> None:
    first = build_storage_key(workspace_id=WS, original_filename="notes.txt")
    second = build_storage_key(workspace_id=WS, original_filename="notes.txt")

    assert first != second


@pytest.mark.parametrize(
    "hostile",
    [
        "../../../etc/passwd",
        "..\\..\\windows\\system32",
        "a/../../b.txt",
        "....//evil.pdf",
    ],
)
def test_traversal_attempts_in_the_filename_cannot_shape_the_key(hostile: str) -> None:
    key = build_storage_key(workspace_id=WS, original_filename=hostile)

    assert ".." not in key
    assert key.count("/") == 1


# --- round trip ---------------------------------------------------------


async def test_put_then_get_round_trips_bytes(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path)
    key = build_storage_key(workspace_id=WS, original_filename="doc.txt")

    await store.put(key, b"hello bytes")

    assert await store.get(key) == b"hello bytes"


async def test_get_missing_key_raises_not_found(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path)
    key = build_storage_key(workspace_id=WS, original_filename="absent.txt")

    with pytest.raises(DocumentNotFoundError):
        await store.get(key)


async def test_delete_is_idempotent(tmp_path: Path) -> None:
    # The queue delivers at least once, so a second delete must not raise.
    store = LocalDocumentStore(tmp_path)
    key = build_storage_key(workspace_id=WS, original_filename="doc.txt")
    await store.put(key, b"x")

    await store.delete(key)
    await store.delete(key)

    with pytest.raises(DocumentNotFoundError):
        await store.get(key)


async def test_stores_under_the_configured_root(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path)
    key = build_storage_key(workspace_id=WS, original_filename="doc.txt")

    await store.put(key, b"x")

    assert (tmp_path / key).is_file()


# --- key validation on read/write --------------------------------------


@pytest.mark.parametrize(
    "bad_key",
    [
        "../escape.txt",
        "/absolute/path.txt",
        "no-slash.txt",
        f"{WS}/../../escape.txt",
        f"{WS}/sub/dir/file.txt",
        "not-a-uuid/also-not.txt",
        "",
    ],
)
async def test_malformed_keys_are_rejected(tmp_path: Path, bad_key: str) -> None:
    # The read path takes keys from the database; a future bug that wrote
    # a hostile key must still not escape the root.
    store = LocalDocumentStore(tmp_path)

    with pytest.raises(DocumentStoreError):
        await store.get(bad_key)
    with pytest.raises(DocumentStoreError):
        await store.put(bad_key, b"x")


async def test_nothing_is_written_outside_the_root(tmp_path: Path) -> None:
    root = tmp_path / "store"
    root.mkdir()
    sentinel = tmp_path / "outside.txt"
    store = LocalDocumentStore(root)

    with pytest.raises(DocumentStoreError):
        await store.put(f"{WS}/../../outside.txt", b"pwned")

    assert not sentinel.exists()
