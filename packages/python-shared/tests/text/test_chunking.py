"""Chunking is asserted with a deterministic word counter, not tiktoken.

Exact chunk boundaries are the thing under test; using real BPE would
make every assertion depend on tokenizer internals and turn a boundary
regression into an unreadable diff. `TiktokenCounter` itself is covered
separately in test_tokenizer.py.
"""

from __future__ import annotations

import pytest

from agentverse_shared.text.chunking import (
    ChunkConfig,
    ContentKind,
    chunk_text,
    detect_content_kind,
)


class WordCounter:
    """1 token == 1 whitespace-separated word."""

    def count(self, text: str) -> int:
        return len(text.split())


COUNTER = WordCounter()


def _contents(chunks: list) -> list[str]:
    return [c.content for c in chunks]


# --- general behavior ---------------------------------------------------


@pytest.mark.parametrize("kind", list(ContentKind))
def test_blank_input_yields_no_chunks(kind: ContentKind) -> None:
    # An empty chunk would embed to noise and pollute retrieval.
    assert chunk_text("   \n\n  ", kind=kind, counter=COUNTER) == []


@pytest.mark.parametrize("kind", list(ContentKind))
def test_every_chunk_respects_the_token_budget(kind: ContentKind) -> None:
    text = "\n\n".join(f"Section {i} " + " ".join(["word"] * 60) for i in range(10))
    config = ChunkConfig(max_tokens=50, overlap_tokens=10)

    chunks = chunk_text(text, kind=kind, counter=COUNTER, config=config)

    assert chunks
    for chunk in chunks:
        assert chunk.token_count <= config.max_tokens, chunk.content


@pytest.mark.parametrize("kind", list(ContentKind))
def test_chunk_indexes_are_sequential_from_zero(kind: ContentKind) -> None:
    text = "\n\n".join(" ".join(["word"] * 40) for _ in range(6))

    chunks = chunk_text(
        text, kind=kind, counter=COUNTER, config=ChunkConfig(max_tokens=50, overlap_tokens=5)
    )

    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_reported_token_count_matches_the_counter() -> None:
    chunks = chunk_text("one two three", kind=ContentKind.PROSE, counter=COUNTER)

    assert len(chunks) == 1
    assert chunks[0].token_count == 3


# --- prose --------------------------------------------------------------


def test_prose_packs_multiple_small_paragraphs_into_one_chunk() -> None:
    text = "First para here.\n\nSecond para here.\n\nThird para here."

    chunks = chunk_text(
        text,
        kind=ContentKind.PROSE,
        counter=COUNTER,
        config=ChunkConfig(max_tokens=50, overlap_tokens=5),
    )

    assert len(chunks) == 1
    assert "First" in chunks[0].content and "Third" in chunks[0].content


def test_prose_overlap_repeats_trailing_content_into_the_next_chunk() -> None:
    paras = [f"para{i} " + " ".join(["w"] * 9) for i in range(6)]
    text = "\n\n".join(paras)

    chunks = chunk_text(
        text,
        kind=ContentKind.PROSE,
        counter=COUNTER,
        config=ChunkConfig(max_tokens=30, overlap_tokens=12),
    )

    assert len(chunks) > 1
    # The tail of chunk 0 must reappear at the head of chunk 1 — that is
    # what prevents an answer spanning a chunk boundary from losing context.
    last_para_of_first = chunks[0].content.split("\n\n")[-1]
    assert chunks[1].content.startswith(last_para_of_first)


def test_prose_zero_overlap_does_not_repeat_content() -> None:
    paras = [f"para{i} " + " ".join(["w"] * 9) for i in range(4)]

    chunks = chunk_text(
        "\n\n".join(paras),
        kind=ContentKind.PROSE,
        counter=COUNTER,
        config=ChunkConfig(max_tokens=30, overlap_tokens=0),
    )

    assert len(chunks) > 1
    first_para_of_second = chunks[1].content.split("\n\n")[0]
    assert first_para_of_second not in chunks[0].content


def test_prose_splits_a_single_oversized_paragraph_by_sentence() -> None:
    # One paragraph, no blank lines — must still come out within budget.
    text = " ".join(f"Sentence number {i} has some words in it." for i in range(20))

    chunks = chunk_text(
        text,
        kind=ContentKind.PROSE,
        counter=COUNTER,
        config=ChunkConfig(max_tokens=30, overlap_tokens=0),
    )

    assert len(chunks) > 1
    assert all(c.token_count <= 30 for c in chunks)


def test_prose_hard_splits_text_with_no_whitespace_boundary() -> None:
    # Pathological input (a minified blob): no sentence, line, or word
    # boundary exists, so only the character-level fallback can save it.
    text = "x" * 500

    chunks = chunk_text(
        text,
        kind=ContentKind.PROSE,
        counter=COUNTER,
        config=ChunkConfig(max_tokens=5, overlap_tokens=0),
    )

    assert chunks
    assert "".join(_contents(chunks)) == text


# --- markdown -----------------------------------------------------------


def test_markdown_does_not_merge_two_unrelated_sections() -> None:
    text = "# Alpha\n\nAlpha body.\n\n# Beta\n\nBeta body."

    chunks = chunk_text(
        text,
        kind=ContentKind.MARKDOWN,
        counter=COUNTER,
        config=ChunkConfig(max_tokens=100, overlap_tokens=0),
    )

    # Both sections fit in one budget, but heading boundaries are hard —
    # merging them would make a retrieval hit cite the wrong section.
    assert len(chunks) == 2
    assert chunks[0].content.startswith("# Alpha")
    assert chunks[1].content.startswith("# Beta")


def test_markdown_repeats_the_heading_when_a_section_spans_chunks() -> None:
    body = "\n\n".join(" ".join(["w"] * 20) for _ in range(5))
    text = f"## Config Reference\n\n{body}"

    chunks = chunk_text(
        text,
        kind=ContentKind.MARKDOWN,
        counter=COUNTER,
        config=ChunkConfig(max_tokens=40, overlap_tokens=0),
    )

    assert len(chunks) > 1
    assert all(c.content.startswith("## Config Reference") for c in chunks)


def test_markdown_keeps_content_before_the_first_heading() -> None:
    text = "Preamble sentence.\n\n# Later Heading\n\nBody."

    chunks = chunk_text(text, kind=ContentKind.MARKDOWN, counter=COUNTER)

    assert any("Preamble sentence." in c.content for c in chunks)


def test_markdown_heading_budget_accounts_for_the_repeated_prefix() -> None:
    heading = "### " + " ".join(["H"] * 10)
    body = "\n\n".join(" ".join(["w"] * 8) for _ in range(6))

    chunks = chunk_text(
        f"{heading}\n\n{body}",
        kind=ContentKind.MARKDOWN,
        counter=COUNTER,
        config=ChunkConfig(max_tokens=30, overlap_tokens=0),
    )

    # Budget must include the heading that gets prepended to each chunk,
    # not just the body packed into it.
    assert all(c.token_count <= 30 for c in chunks)


# --- code ---------------------------------------------------------------


def test_code_splits_at_top_level_definitions() -> None:
    text = "import os\n\ndef alpha():\n    return 1\n\ndef beta():\n    return 2\n"

    chunks = chunk_text(
        text,
        kind=ContentKind.CODE,
        counter=COUNTER,
        config=ChunkConfig(max_tokens=8, overlap_tokens=0),
    )

    joined = _contents(chunks)
    # `def alpha` and `def beta` must not end up in the same chunk at this
    # budget, and the import preamble is its own unit.
    assert any("import os" in c for c in joined)
    assert not any("def alpha" in c and "def beta" in c for c in joined)


def test_code_keeps_a_small_function_intact() -> None:
    text = "def only():\n    x = 1\n    return x\n"

    chunks = chunk_text(text, kind=ContentKind.CODE, counter=COUNTER)

    assert len(chunks) == 1
    assert "return x" in chunks[0].content


def test_code_recognizes_non_python_definitions() -> None:
    text = "export function alpha() {\n  return 1;\n}\nexport function beta() {\n  return 2;\n}\n"

    chunks = chunk_text(
        text,
        kind=ContentKind.CODE,
        counter=COUNTER,
        config=ChunkConfig(max_tokens=6, overlap_tokens=0),
    )

    assert not any("alpha" in c and "beta" in c for c in _contents(chunks))


# --- structured ---------------------------------------------------------


def test_structured_csv_repeats_the_header_in_every_chunk() -> None:
    rows = "\n".join(f"row{i},value{i},extra{i}" for i in range(20))
    text = f"name,value,extra\n{rows}"

    chunks = chunk_text(
        text,
        kind=ContentKind.STRUCTURED,
        counter=COUNTER,
        config=ChunkConfig(max_tokens=12, overlap_tokens=0),
    )

    assert len(chunks) > 1
    # Without the header, chunk 2+ is unlabeled values that retrieval
    # cannot interpret.
    assert all(c.content.startswith("name,value,extra") for c in chunks)


def test_structured_jsonl_is_not_treated_as_headed_csv() -> None:
    text = "\n".join(f'{{"a": {i}}}' for i in range(10))

    chunks = chunk_text(
        text,
        kind=ContentKind.STRUCTURED,
        counter=COUNTER,
        config=ChunkConfig(max_tokens=4, overlap_tokens=0),
    )

    # The first JSON object is a record, not a header, so it must appear
    # exactly once across all chunks.
    assert sum(c.content.count('{"a": 0}') for c in chunks) == 1


def test_structured_never_splits_mid_row() -> None:
    text = "id,name\n" + "\n".join(f"{i},name{i}" for i in range(10))

    chunks = chunk_text(
        text,
        kind=ContentKind.STRUCTURED,
        counter=COUNTER,
        config=ChunkConfig(max_tokens=10, overlap_tokens=0),
    )

    for chunk in chunks:
        for line in chunk.content.splitlines()[1:]:
            assert "," in line


# --- kind detection ----------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("notes.md", ContentKind.MARKDOWN),
        ("README.markdown", ContentKind.MARKDOWN),
        ("data.csv", ContentKind.STRUCTURED),
        ("events.jsonl", ContentKind.STRUCTURED),
        ("config.json", ContentKind.STRUCTURED),
        ("main.py", ContentKind.CODE),
        ("app.tsx", ContentKind.CODE),
        ("lib.rs", ContentKind.CODE),
        ("report.pdf", ContentKind.PROSE),
        ("memo.docx", ContentKind.PROSE),
        ("plain.txt", ContentKind.PROSE),
    ],
)
def test_detect_content_kind_prefers_the_extension(filename: str, expected: ContentKind) -> None:
    # Declared MIME is deliberately wrong here: the extension must win,
    # since a client-supplied content type is untrusted input.
    assert detect_content_kind(filename, "application/octet-stream") == expected


def test_detect_content_kind_falls_back_to_mime_when_extension_is_unknown() -> None:
    assert detect_content_kind("noextension", "text/markdown") == ContentKind.MARKDOWN
    assert detect_content_kind("noextension", "text/csv") == ContentKind.STRUCTURED


def test_detect_content_kind_defaults_to_prose() -> None:
    assert detect_content_kind("mystery.xyz", "application/weird") == ContentKind.PROSE


# --- config validation -------------------------------------------------


def test_overlap_must_be_smaller_than_max_tokens() -> None:
    # Equal values would make the carried overlap fill each chunk and
    # packing could never advance — an infinite loop, so it must raise.
    with pytest.raises(ValueError, match="overlap_tokens must be smaller"):
        ChunkConfig(max_tokens=100, overlap_tokens=100)


def test_max_tokens_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_tokens must be positive"):
        ChunkConfig(max_tokens=0)
