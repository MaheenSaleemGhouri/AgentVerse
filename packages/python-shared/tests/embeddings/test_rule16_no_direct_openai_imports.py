"""CLAUDE.md Rule 16 for the shared package: exactly one file may import
the OpenAI SDK.

Mirrors apps/api's equivalent check. Added when Phase 5 introduced an
embedding provider here — without it, the shared package would be an
unguarded back door around the rule apps/api enforces strictly.

Includes the self-checks apps/api's version was missing: that one shipped
with a wrong `_SRC_ROOT` and passed vacuously for three phases while
enforcing nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "agentverse_shared"
_ALLOWED_FILE = _SRC_ROOT / "embeddings" / "openai_provider.py"
_IMPORT_PATTERN = re.compile(r"^\s*(import openai\b|from openai\b)")


def test_scans_real_source_files() -> None:
    assert _SRC_ROOT.is_dir(), f"_SRC_ROOT does not exist: {_SRC_ROOT}"
    assert len(list(_SRC_ROOT.rglob("*.py"))) > 3
    assert _ALLOWED_FILE.is_file(), f"_ALLOWED_FILE does not exist: {_ALLOWED_FILE}"


def test_the_pattern_actually_matches_an_import() -> None:
    assert _IMPORT_PATTERN.match("import openai")
    assert _IMPORT_PATTERN.match("from openai import AsyncOpenAI")
    assert _IMPORT_PATTERN.match("# import openai") is None


def test_only_the_embedding_provider_imports_the_openai_sdk() -> None:
    offending: list[str] = []
    for path in _SRC_ROOT.rglob("*.py"):
        if path == _ALLOWED_FILE:
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _IMPORT_PATTERN.match(line):
                offending.append(f"{path.relative_to(_SRC_ROOT)}:{line_no}: {line.strip()}")

    assert offending == [], (
        f"Rule 16 violation — `openai` imported outside {_ALLOWED_FILE.name}: {offending}"
    )
