"""The assistant's grounding corpus: the published guides, split into
heading-bounded passages.

**The markdown under `apps/web/content/docs/` is the single source of
truth.** This module builds a JSON index from it, `scripts/build_docs_index.py`
writes that index, and `tests/unit/test_docs_corpus.py` fails if the
committed file has drifted from the markdown — the same
generated-artifact-plus-drift-gate arrangement `packages/contracts` uses
for the OpenAPI types, and for the same reason: DRY (Rule 3) does not
allow two hand-maintained copies, but the API image cannot read the web
app's content directory at runtime.

Passages are split on `##` headings rather than whole pages because a
whole guide is mostly irrelevant to any one question, and an answer
grounded in "the section about API keys" cites something a reader can
actually jump to.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Final

from agentverse_api.assistant_service.domain.entities import DocPassage

INDEX_PATH: Final[Path] = Path(__file__).with_name("docs_index.json")
"""Ships inside the package, so the running API needs no repo checkout."""

_FRONTMATTER: Final[re.Pattern[str]] = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_FIELD: Final[re.Pattern[str]] = re.compile(r"^([a-z_]+):\s*(.*)$")
_HEADING: Final[re.Pattern[str]] = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_FENCE: Final[re.Pattern[str]] = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
_NON_SLUG: Final[re.Pattern[str]] = re.compile(r"[^\w\s-]|_")
_WHITESPACE: Final[re.Pattern[str]] = re.compile(r"\s+")

MAX_PASSAGE_CHARS: Final[int] = 1_800
"""A passage longer than this is truncated on a word boundary. Four of
these plus the system prompt and history stay well inside the budget
CLAUDE.md §4 requires context assembly to respect."""


class CorpusError(RuntimeError):
    """The markdown could not be parsed. Raised loudly at build time —
    a silently skipped guide is a hole in the assistant's knowledge that
    shows up as a confidently wrong answer weeks later."""


def _frontmatter(source: str, *, path: Path) -> dict[str, str]:
    """Parses the narrow key/value frontmatter these guides actually use.

    Deliberately not a YAML parser: the schema is six scalar fields fixed
    by `apps/web/lib/docs/types.ts`, and anything richer appearing here
    should fail rather than be half-understood.
    """
    match = _FRONTMATTER.match(source)
    if match is None:
        raise CorpusError(f"{path}: no frontmatter block")

    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        field = _FIELD.match(line)
        if field is None:
            raise CorpusError(f"{path}: frontmatter line is not `key: value` — {line!r}")
        fields[field.group(1)] = field.group(2).strip().strip('"')
    return fields


def slugify_heading(heading: str) -> str:
    """Must match `apps/web/lib/docs/render.ts`'s `slugifyHeading`, or a
    cited anchor lands the reader at the top of the page instead of at
    the section the answer came from.

    That function drops punctuation rather than replacing it, so
    "What's next?" is `whats-next`, not `what-s-next` — the difference
    is a dead link, and a dead link in a citation undermines the one
    thing citations are for. `\\w` is narrowed by also stripping
    underscores, matching the frontend's `[^\\p{L}\\p{N}\\s-]`.
    """
    stripped = _NON_SLUG.sub("", heading.lower())
    return _WHITESPACE.sub("-", stripped.strip())


def _truncate(text: str) -> str:
    if len(text) <= MAX_PASSAGE_CHARS:
        return text
    cut = text[:MAX_PASSAGE_CHARS].rsplit(" ", 1)[0]
    return f"{cut}…"


def _sections(body: str) -> list[tuple[str, str]]:
    """`(heading, text)` for each `##` section, plus the intro under the
    synthetic heading `Overview`."""
    matches = list(_HEADING.finditer(body))
    sections: list[tuple[str, str]] = []

    intro = body[: matches[0].start()] if matches else body
    if intro.strip():
        sections.append(("Overview", intro.strip()))

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        text = body[match.end() : end].strip()
        if text:
            sections.append((match.group(1).strip(), text))
    return sections


def build_passages(docs_root: Path) -> list[DocPassage]:
    """Every passage of every *published* guide, in stable path order.

    Stable order matters: the index is a committed artifact, and a
    build that reordered it on every run would produce a diff on every
    unrelated PR and train reviewers to ignore it.
    """
    passages: list[DocPassage] = []

    for path in sorted(docs_root.glob("*/*.md")):
        source = path.read_text(encoding="utf-8")
        fields = _frontmatter(source, path=path)

        for required in ("title", "pillar", "status"):
            if required not in fields:
                raise CorpusError(f"{path}: frontmatter is missing `{required}`")

        # Drafts and deprecated guides are excluded on purpose. The
        # assistant should never ground an answer in a page the product
        # does not currently publish.
        if fields["status"] != "published":
            continue

        if fields["pillar"] != path.parent.name:
            raise CorpusError(
                f"{path}: pillar {fields['pillar']!r} does not match directory {path.parent.name!r}"
            )

        body = source[_FRONTMATTER.match(source).end() :]  # type: ignore[union-attr]
        # Code fences are stripped from the *grounding* text: a curl
        # snippet is high-noise for term matching and, quoted back, is
        # the thing the assistant is most likely to get subtly wrong.
        # The citation link takes the reader to the real, runnable one.
        body = _FENCE.sub("", body)

        page_url = f"/docs/{fields['pillar']}/{path.stem}"
        for heading, text in _sections(body):
            anchor = "" if heading == "Overview" else f"#{slugify_heading(heading)}"
            passages.append(
                DocPassage(
                    doc_title=fields["title"],
                    heading=heading,
                    url=f"{page_url}{anchor}",
                    text=_truncate(" ".join(text.split())),
                )
            )

    if not passages:
        raise CorpusError(f"{docs_root}: no published guides found")
    return passages


def serialize(passages: list[DocPassage]) -> str:
    """The exact bytes of the committed index — the drift test compares
    against this, so formatting has to be deterministic."""
    return json.dumps([asdict(passage) for passage in passages], indent=2, sort_keys=True) + "\n"


def load_passages(path: Path = INDEX_PATH) -> list[DocPassage]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [DocPassage(**entry) for entry in raw]
