"""Structurally enforces CLAUDE.md Rule 16 for the Anthropic SDK, exactly
as `test_rule16_no_direct_openai_imports.py` does for `openai`: grepping
any file outside `orchestration_service/infrastructure/providers/` for
`import anthropic` must find zero matches.
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "agentverse_api"
_ALLOWED_DIR = _SRC_ROOT / "orchestration_service" / "infrastructure" / "providers"
_IMPORT_PATTERN = re.compile(r"^\s*(import anthropic\b|from anthropic\b)")


def test_scans_real_source_files() -> None:
    assert _SRC_ROOT.is_dir(), f"_SRC_ROOT does not exist: {_SRC_ROOT}"
    assert len(list(_SRC_ROOT.rglob("*.py"))) > 10
    assert _ALLOWED_DIR.is_dir(), f"_ALLOWED_DIR does not exist: {_ALLOWED_DIR}"


def test_the_pattern_actually_matches_an_import() -> None:
    assert _IMPORT_PATTERN.match("import anthropic")
    assert _IMPORT_PATTERN.match("from anthropic import AsyncAnthropic")
    assert _IMPORT_PATTERN.match("    from anthropic import AsyncAnthropic")
    assert _IMPORT_PATTERN.match("# import anthropic") is None
    assert _IMPORT_PATTERN.match("import anthropic_unrelated_package") is None


def test_only_the_anthropic_adapter_imports_the_anthropic_sdk() -> None:
    offending: list[str] = []
    for path in _SRC_ROOT.rglob("*.py"):
        if _ALLOWED_DIR in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _IMPORT_PATTERN.match(line):
                offending.append(f"{path.relative_to(_SRC_ROOT)}:{line_no}: {line.strip()}")

    assert offending == [], (
        "Rule 16 violation — `anthropic` imported outside "
        f"orchestration_service/infrastructure/providers/: {offending}"
    )
