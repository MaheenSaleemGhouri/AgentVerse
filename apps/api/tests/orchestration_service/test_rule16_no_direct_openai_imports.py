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

# parents[2] is apps/api — parents[1] (tests/) was a bug that made this
# check scan a nonexistent `tests/src/agentverse_api`, glob zero files,
# and pass vacuously from Phase 2 until Phase 5 caught it. The
# `_scans_real_source_files` test below now pins that down so the same
# silent-no-op regression cannot return.
_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "agentverse_api"
_ALLOWED_DIR = _SRC_ROOT / "orchestration_service" / "infrastructure" / "providers"
_IMPORT_PATTERN = re.compile(r"^\s*(import openai\b|from openai\b)")


def test_scans_real_source_files() -> None:
    """Guards the guard: a wrong `_SRC_ROOT` makes the check below pass
    while enforcing nothing, which is worse than not having it.
    """
    assert _SRC_ROOT.is_dir(), f"_SRC_ROOT does not exist: {_SRC_ROOT}"
    assert len(list(_SRC_ROOT.rglob("*.py"))) > 10
    assert _ALLOWED_DIR.is_dir(), f"_ALLOWED_DIR does not exist: {_ALLOWED_DIR}"


def test_the_pattern_actually_matches_an_import() -> None:
    """Guards the regex: a typo'd pattern is the other way this check can
    silently stop enforcing.
    """
    assert _IMPORT_PATTERN.match("import openai")
    assert _IMPORT_PATTERN.match("from openai import AsyncOpenAI")
    assert _IMPORT_PATTERN.match("    from openai import AsyncOpenAI")
    assert _IMPORT_PATTERN.match("# import openai") is None
    # `\bopenai\b` must not fire on an unrelated package whose name merely
    # starts with the same letters.
    assert _IMPORT_PATTERN.match("import openai_unrelated_package") is None


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
