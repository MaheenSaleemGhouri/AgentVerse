"""The drift gate, plus the parsing rules it depends on."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentverse_api.assistant_service.infrastructure.docs_corpus import (
    INDEX_PATH,
    CorpusError,
    build_passages,
    serialize,
    slugify_heading,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
DOCS_ROOT = REPO_ROOT / "apps" / "web" / "content" / "docs"

_PUBLISHED = """\
---
title: Connect a tool
summary: A summary.
pillar: agent-builder
last_verified: "2026-08-07"
status: published
order: 2
---

Intro paragraph.

## First section

Body of the first section.

```bash
curl -X POST https://example.invalid/should-not-appear
```

## Second section

Body of the second.
"""


def _write(root: Path, pillar: str, name: str, source: str) -> None:
    directory = root / pillar
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(source, encoding="utf-8")


def test_committed_index_matches_the_markdown() -> None:
    """The whole point of the artifact: if this fails the assistant is
    answering from documentation that no longer exists."""
    rebuilt = serialize(build_passages(DOCS_ROOT))
    assert rebuilt == INDEX_PATH.read_text(encoding="utf-8"), (
        "docs_index.json is stale — run `uv run python scripts/build_docs_index.py`"
    )


def test_splits_on_headings_and_keeps_the_intro(tmp_path: Path) -> None:
    _write(tmp_path, "agent-builder", "tools.md", _PUBLISHED)

    passages = build_passages(tmp_path)

    assert [passage.heading for passage in passages] == [
        "Overview",
        "First section",
        "Second section",
    ]
    assert passages[0].url == "/docs/agent-builder/tools"
    assert passages[1].url == "/docs/agent-builder/tools#first-section"


def test_code_fences_are_stripped_from_grounding_text(tmp_path: Path) -> None:
    """A quoted-back curl snippet is what the assistant is most likely to
    get subtly wrong; the citation link carries the runnable one."""
    _write(tmp_path, "agent-builder", "tools.md", _PUBLISHED)

    passages = build_passages(tmp_path)

    assert all("should-not-appear" not in passage.text for passage in passages)


def test_unpublished_guides_are_excluded(tmp_path: Path) -> None:
    _write(tmp_path, "agent-builder", "tools.md", _PUBLISHED)
    _write(
        tmp_path,
        "agent-builder",
        "draft.md",
        _PUBLISHED.replace("status: published", "status: draft"),
    )

    passages = build_passages(tmp_path)

    assert {passage.url.split("#")[0] for passage in passages} == {"/docs/agent-builder/tools"}


def test_pillar_directory_mismatch_fails_loudly(tmp_path: Path) -> None:
    _write(tmp_path, "orchestration", "tools.md", _PUBLISHED)

    with pytest.raises(CorpusError, match="does not match directory"):
        build_passages(tmp_path)


def test_missing_frontmatter_fails_loudly(tmp_path: Path) -> None:
    _write(tmp_path, "agent-builder", "tools.md", "no frontmatter here\n")

    with pytest.raises(CorpusError, match="no frontmatter"):
        build_passages(tmp_path)


def test_an_empty_corpus_is_an_error_not_an_empty_index(tmp_path: Path) -> None:
    """Silently producing zero passages would ship an assistant that
    answers "I could not find that" to every question."""
    with pytest.raises(CorpusError, match="no published guides"):
        build_passages(tmp_path)


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("First section", "first-section"),
        ("Roles & permissions", "roles-permissions"),
        # Punctuation is dropped, not turned into a separator — matching
        # the frontend exactly matters here, because a mismatch is a
        # citation that lands on the wrong part of the page.
        ("What's next?", "whats-next"),
        ("Rate limits (per plan)", "rate-limits-per-plan"),
    ],
)
def test_heading_slugs_match_the_frontend(heading: str, expected: str) -> None:
    """Must agree with `apps/web/lib/docs/render.ts`, or a cited anchor
    lands the reader at the top of the page."""
    assert slugify_heading(heading) == expected
