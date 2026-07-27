from __future__ import annotations

from agentverse_shared.retrieval.rewrite import (
    MAX_QUERY_CHARS,
    extract_keywords,
    normalize_query,
    rewrite_query,
)


def test_collapses_whitespace_and_trims() -> None:
    assert normalize_query("  how   do\n\tI  cancel ") == "how do I cancel"


def test_nfkc_folds_pasted_compatibility_characters() -> None:
    # Full-width text out of a PDF paste must embed where typed text does.
    assert normalize_query("ｃａｎｃｅｌ") == "cancel"


def test_caps_query_length() -> None:
    assert len(normalize_query("a" * (MAX_QUERY_CHARS + 500))) == MAX_QUERY_CHARS


def test_semantic_query_keeps_the_full_question() -> None:
    """The vector arm must not get a stopword-stripped query — embeddings
    encode intent, and the scaffold words carry some of it.
    """
    assert rewrite_query("How do I cancel my subscription?").semantic_query == (
        "How do I cancel my subscription?"
    )


def test_keyword_query_drops_stopwords_and_keeps_content_terms() -> None:
    rewritten = rewrite_query("How do I cancel my subscription?")
    assert rewritten.keywords == ["cancel", "subscription"]
    assert rewritten.keyword_query == "cancel subscription"


def test_keywords_are_deduplicated_in_first_seen_order() -> None:
    assert extract_keywords("billing billing invoice billing") == ["billing", "invoice"]


def test_single_characters_are_dropped() -> None:
    # A one-character FTS term matches everywhere and ranks nothing.
    assert extract_keywords("a b agent") == ["agent"]


def test_all_stopword_query_yields_an_empty_keyword_query() -> None:
    """Callers must distinguish "no content terms" from "match everything"
    — an empty keyword query is the signal to skip the arm entirely.
    """
    rewritten = rewrite_query("what is it?")
    assert rewritten.keyword_query == ""
    assert rewritten.keywords == []


def test_hyphenated_and_dotted_terms_survive() -> None:
    assert extract_keywords("rate-limit config.yaml") == ["rate-limit", "config.yaml"]


def test_original_query_is_preserved_verbatim() -> None:
    assert rewrite_query("  Weird   Spacing  ").original == "  Weird   Spacing  "
