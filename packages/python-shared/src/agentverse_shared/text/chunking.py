"""Content-aware chunking.

Pure functions, zero I/O — `vector-database-expert` requires chunking be
unit-testable per content type ("chunking bugs silently degrade every
downstream RAG answer") and explicitly forbids one global chunk size for
all content, because a fixed size fragments code mid-function and breaks
markdown mid-section.

Four content kinds, one shared packing algorithm:

- **prose** — paragraph units, greedy pack to a token budget with overlap.
- **markdown** — heading-bounded sections; a section spanning multiple
  chunks repeats its heading so each chunk stays self-describing.
- **code** — top-level `def`/`class`-style block units, so a function is
  not split across chunks unless it alone exceeds the budget.
- **structured** — line units (CSV rows, JSON-lines); a CSV header row
  repeats in every chunk so column meaning survives retrieval.

Token counting is injected (`TokenCounter`), never imported here, so
these functions stay pure and tests can assert exact boundaries with a
trivial deterministic counter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from agentverse_shared.text.tokenizer import TokenCounter


class ContentKind(StrEnum):
    PROSE = "prose"
    MARKDOWN = "markdown"
    CODE = "code"
    STRUCTURED = "structured"


@dataclass(frozen=True, slots=True)
class ChunkConfig:
    """Per-kind sizing. Defaults follow `vector-database-expert`'s stated
    baseline for prose (~500 tokens, ~50-100 overlap); the other kinds
    deviate for documented structural reasons, not by preference.
    """

    max_tokens: int = 500
    overlap_tokens: int = 75

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if self.overlap_tokens < 0:
            raise ValueError("overlap_tokens must not be negative")
        if self.overlap_tokens >= self.max_tokens:
            # Otherwise the carried overlap alone fills every chunk and
            # packing cannot advance — an infinite loop, not a bad result.
            raise ValueError("overlap_tokens must be smaller than max_tokens")


#: Per-kind defaults. Code gets a larger budget and no overlap: a
#: duplicated half-function is noise in retrieval, and function
#: boundaries already make chunks self-contained. Structured data gets no
#: overlap because a repeated row is a duplicate record, not context.
DEFAULT_CONFIGS: dict[ContentKind, ChunkConfig] = {
    ContentKind.PROSE: ChunkConfig(max_tokens=500, overlap_tokens=75),
    ContentKind.MARKDOWN: ChunkConfig(max_tokens=500, overlap_tokens=50),
    ContentKind.CODE: ChunkConfig(max_tokens=800, overlap_tokens=0),
    ContentKind.STRUCTURED: ChunkConfig(max_tokens=400, overlap_tokens=0),
}


@dataclass(frozen=True, slots=True)
class TextChunk:
    index: int
    content: str
    token_count: int


_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+\S")
# Top-level (column-0) definition starts across the languages a user is
# plausibly uploading. Deliberately conservative: a missed boundary just
# means a larger unit that the packer still splits safely, whereas a
# false boundary would cut a function in half.
_CODE_BLOCK_START = re.compile(
    r"^(?:"
    r"def\s|class\s|async\s+def\s"  # Python
    r"|(?:export\s+)?(?:async\s+)?function\s"  # JS/TS
    r"|(?:export\s+)?(?:default\s+)?class\s"
    r"|(?:public|private|protected|static)\s"  # Java/C#-ish
    r"|func\s"  # Go
    r"|fn\s|impl\s|pub\s+fn\s"  # Rust
    r")"
)


def chunk_text(
    text: str,
    *,
    kind: ContentKind,
    counter: TokenCounter,
    config: ChunkConfig | None = None,
) -> list[TextChunk]:
    """Splits `text` into retrievable chunks using the strategy for `kind`.

    Returns an empty list for blank input — an empty document must not
    produce a single empty chunk that would later embed to noise.
    """
    resolved = config if config is not None else DEFAULT_CONFIGS[kind]
    if not text.strip():
        return []

    if kind is ContentKind.MARKDOWN:
        pieces = _chunk_markdown(text, resolved, counter)
    elif kind is ContentKind.CODE:
        pieces = _pack(_code_units(text), resolved, counter, joiner="\n")
    elif kind is ContentKind.STRUCTURED:
        pieces = _chunk_structured(text, resolved, counter)
    else:
        pieces = _pack(_prose_units(text), resolved, counter, joiner="\n\n")

    return [
        TextChunk(index=i, content=piece, token_count=counter.count(piece))
        for i, piece in enumerate(pieces)
    ]


def detect_content_kind(filename: str, content_type: str) -> ContentKind:
    """Maps an upload to its chunking strategy.

    Extension-driven with the declared MIME type as a fallback only —
    `secure-coding-expert` treats a client-declared `Content-Type` as
    untrusted, and this choice only affects chunk shape (never a
    security decision), so the more specific signal wins.
    """
    lowered = filename.lower()
    suffix = lowered.rsplit(".", 1)[-1] if "." in lowered else ""

    if suffix in {"md", "markdown", "mdx"}:
        return ContentKind.MARKDOWN
    if suffix in {"csv", "tsv", "json", "jsonl", "ndjson"}:
        return ContentKind.STRUCTURED
    if suffix in {
        "py",
        "js",
        "ts",
        "tsx",
        "jsx",
        "go",
        "rs",
        "java",
        "cs",
        "rb",
        "php",
        "c",
        "h",
        "cpp",
        "hpp",
        "kt",
        "swift",
        "sh",
        "sql",
    }:
        return ContentKind.CODE
    if suffix in {"txt", "pdf", "docx", "doc", "rtf"}:
        return ContentKind.PROSE

    if content_type == "text/markdown":
        return ContentKind.MARKDOWN
    if content_type in {"text/csv", "application/json", "application/x-ndjson"}:
        return ContentKind.STRUCTURED
    return ContentKind.PROSE


# --- unit extraction ---------------------------------------------------


def _prose_units(text: str) -> list[str]:
    return [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]


def _code_units(text: str) -> list[str]:
    """Groups lines into top-level definition blocks.

    Everything before the first definition (imports, module docstring)
    becomes its own leading unit rather than being glued onto the first
    function, so a retrieval hit on an import block cites the right span.
    """
    lines = text.splitlines()
    units: list[str] = []
    current: list[str] = []

    for line in lines:
        if _CODE_BLOCK_START.match(line) and current:
            units.append("\n".join(current).strip("\n"))
            current = [line]
        else:
            current.append(line)

    if current:
        tail = "\n".join(current).strip("\n")
        if tail:
            units.append(tail)
    return [u for u in units if u.strip()]


def _chunk_structured(text: str, config: ChunkConfig, counter: TokenCounter) -> list[str]:
    """Line-per-record packing.

    A delimited first line is treated as a header and repeated at the top
    of every chunk: without it, chunk 2 onward is a wall of values whose
    columns are unidentifiable, which retrieval cannot recover from.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    header = lines[0]
    looks_delimited = ("," in header or "\t" in header) and not header.lstrip().startswith(
        ("{", "[")
    )

    if not looks_delimited or len(lines) == 1:
        return _pack(lines, config, counter, joiner="\n")

    body_chunks = _pack(
        lines[1:], config, counter, joiner="\n", reserved_tokens=counter.count(header) + 1
    )
    return [f"{header}\n{chunk}" for chunk in body_chunks]


def _chunk_markdown(text: str, config: ChunkConfig, counter: TokenCounter) -> list[str]:
    """Heading-bounded sections, each packed independently.

    Packing per section (rather than across the whole document) is what
    makes this genuinely heading-aware: two unrelated sections never land
    in one chunk just because they were both small.
    """
    sections = _markdown_sections(text)
    chunks: list[str] = []

    for heading, body in sections:
        units = _prose_units(body)
        if not units:
            if heading:
                chunks.append(heading)
            continue

        reserved = counter.count(heading) + 1 if heading else 0
        for piece in _pack(units, config, counter, joiner="\n\n", reserved_tokens=reserved):
            chunks.append(f"{heading}\n{piece}" if heading else piece)

    return chunks


def _markdown_sections(text: str) -> list[tuple[str, str]]:
    """Splits into `(heading_line, body)` pairs. Content before the first
    heading is returned with an empty heading rather than dropped.
    """
    sections: list[tuple[str, str]] = []
    heading = ""
    body: list[str] = []

    for line in text.splitlines():
        if _MARKDOWN_HEADING.match(line):
            if heading or any(b.strip() for b in body):
                sections.append((heading, "\n".join(body)))
            heading = line.strip()
            body = []
        else:
            body.append(line)

    if heading or any(b.strip() for b in body):
        sections.append((heading, "\n".join(body)))
    return sections


# --- packing -----------------------------------------------------------


def _pack(
    units: list[str],
    config: ChunkConfig,
    counter: TokenCounter,
    *,
    joiner: str,
    reserved_tokens: int = 0,
) -> list[str]:
    """Greedily packs `units` into chunks under the token budget.

    `reserved_tokens` accounts for text the caller will prepend to every
    chunk (a markdown heading, a CSV header) so the final chunk still
    fits the budget once that prefix is added — computing the budget
    without it is how "500-token" chunks silently become 540.
    """
    budget = max(1, config.max_tokens - reserved_tokens)
    expanded: list[str] = []
    for unit in units:
        if counter.count(unit) <= budget:
            expanded.append(unit)
        else:
            expanded.extend(_split_oversized(unit, budget, counter))

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for unit in expanded:
        unit_tokens = counter.count(unit)
        if current and current_tokens + unit_tokens > budget:
            chunks.append(joiner.join(current))
            current = _overlap_tail(current, config.overlap_tokens, counter)
            current_tokens = sum(counter.count(u) for u in current)
        current.append(unit)
        current_tokens += unit_tokens

    if current:
        chunks.append(joiner.join(current))
    return chunks


def _overlap_tail(units: list[str], overlap_tokens: int, counter: TokenCounter) -> list[str]:
    """The trailing units of a just-emitted chunk to carry into the next.

    Never returns every unit: carrying the whole chunk forward would mean
    the next chunk starts already full and packing could not advance.
    """
    if overlap_tokens <= 0 or len(units) < 2:
        return []

    tail: list[str] = []
    total = 0
    for unit in reversed(units[1:]):
        unit_tokens = counter.count(unit)
        if total + unit_tokens > overlap_tokens:
            break
        tail.insert(0, unit)
        total += unit_tokens
    return tail


def _split_oversized(unit: str, budget: int, counter: TokenCounter) -> list[str]:
    """Breaks one over-budget unit down the boundary ladder.

    Sentences, then lines, then words, then a character-level binary
    search as the last resort — so a single pathological unit (a minified
    line, a table with no spaces) still yields in-budget chunks instead
    of one oversized chunk the embedding call would reject.
    """
    for splitter in (_by_sentence, _by_line, _by_word):
        parts = splitter(unit)
        if len(parts) > 1:
            out: list[str] = []
            for part in parts:
                if counter.count(part) <= budget:
                    out.append(part)
                else:
                    out.extend(_split_oversized(part, budget, counter))
            return _recombine(out, budget, counter)
    return _hard_split(unit, budget, counter)


def _by_sentence(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _by_line(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def _by_word(text: str) -> list[str]:
    return text.split()


def _recombine(parts: list[str], budget: int, counter: TokenCounter) -> list[str]:
    """Re-merges over-split fragments back up to the budget, so splitting
    one long paragraph by sentence doesn't emit one tiny chunk per
    sentence.
    """
    merged: list[str] = []
    current = ""
    for part in parts:
        candidate = f"{current} {part}".strip() if current else part
        if current and counter.count(candidate) > budget:
            merged.append(current)
            current = part
        else:
            current = candidate
    if current:
        merged.append(current)
    return merged


def _hard_split(text: str, budget: int, counter: TokenCounter) -> list[str]:
    """Character-level split via binary search on the token count.

    Only reachable for text with no sentence, line, or whitespace
    boundary at all. Binary search (not a fixed chars-per-token guess)
    keeps this correct for any tokenizer.
    """
    out: list[str] = []
    remaining = text

    while remaining:
        if counter.count(remaining) <= budget:
            out.append(remaining)
            break

        low, high, best = 1, len(remaining), 1
        while low <= high:
            mid = (low + high) // 2
            if counter.count(remaining[:mid]) <= budget:
                best = mid
                low = mid + 1
            else:
                high = mid - 1

        out.append(remaining[:best])
        remaining = remaining[best:]
    return out
