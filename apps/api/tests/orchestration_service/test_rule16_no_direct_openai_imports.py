"""Structurally enforces CLAUDE.md Rule 16 for this codebase: "Every LLM
call goes through the provider-abstraction layer — no provider SDK
imported from a route, workflow, or orchestration component." This
phase's acceptance criteria name the check explicitly: grepping any file
outside `orchestration_service/infrastructure/providers/` for
`import openai` must find zero matches.
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "agentverse_api"
_ALLOWED_DIR = _SRC_ROOT / "orchestration_service" / "infrastructure" / "providers"
_IMPORT_PATTERN = re.compile(r"^\s*(import openai\b|from openai\b)")


def test_only_the_openai_adapter_imports_the_openai_sdk() -> None:
    offending: list[str] = []
    for path in _SRC_ROOT.rglob("*.py"):
        if _ALLOWED_DIR in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _IMPORT_PATTERN.match(line):
                offending.append(f"{path.relative_to(_SRC_ROOT)}:{line_no}: {line.strip()}")

    assert offending == [], (
        "Rule 16 violation — `openai` imported outside "
        f"orchestration_service/infrastructure/providers/: {offending}"
    )
