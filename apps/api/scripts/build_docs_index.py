"""Regenerate the assistant's docs index from the published guides.

    uv run python scripts/build_docs_index.py

Run it after editing anything under `apps/web/content/docs/`. If you
forget, `tests/unit/test_docs_corpus.py` fails with the command to run —
the drift gate exists because a stale index is invisible at runtime: the
assistant just quietly answers from last month's documentation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from agentverse_api.assistant_service.infrastructure.docs_corpus import (
    INDEX_PATH,
    build_passages,
    serialize,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_ROOT = REPO_ROOT / "apps" / "web" / "content" / "docs"


def main() -> int:
    if not DOCS_ROOT.is_dir():
        print(f"docs not found at {DOCS_ROOT}", file=sys.stderr)
        return 1

    passages = build_passages(DOCS_ROOT)
    INDEX_PATH.write_text(serialize(passages), encoding="utf-8")
    print(f"wrote {len(passages)} passages to {INDEX_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
