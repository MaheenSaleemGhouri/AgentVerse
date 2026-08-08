"""Retrieval scoring — pure functions, plus a few real questions against
the real corpus.

The corpus assertions are deliberately about *which guide* is retrieved,
never about wording. They are a regression net for the thing that
actually breaks: an edit that renames a heading and quietly stops a
common question from finding its answer.
"""

from __future__ import annotations

import pytest

from agentverse_api.assistant_service.domain.entities import DocPassage
from agentverse_api.assistant_service.infrastructure.docs_corpus import load_passages
from agentverse_api.assistant_service.infrastructure.docs_index import (
    MIN_SCORE,
    CorpusDocsIndex,
    rank,
    score,
    terms,
)


def passage(title: str = "T", heading: str = "H", text: str = "B") -> DocPassage:
    return DocPassage(doc_title=title, heading=heading, url="/docs/x/y", text=text)


def test_stopwords_are_dropped() -> None:
    """Left in, "how do I do the thing" matches every passage equally."""
    assert terms("How do I use the webhook") == {"webhook"}


def test_a_title_match_outweighs_a_body_match() -> None:
    in_title = passage(title="Webhooks", text="unrelated")
    in_body = passage(title="unrelated", text="webhooks")

    assert score({"webhooks"}, in_title) > score({"webhooks"}, in_body)


def test_repetition_does_not_inflate_a_score() -> None:
    """Otherwise the longest passage wins every query."""
    once = passage(text="webhook")
    many = passage(text="webhook webhook webhook webhook")

    assert score({"webhook"}, once) == score({"webhook"}, many)


def test_weak_matches_are_dropped_rather_than_returned() -> None:
    """A passage that shares one incidental word grounds the answer in
    something irrelevant, which reads as a confident non-sequitur."""
    incidental = passage(text="workspace")
    assert score({"workspace"}, incidental) < MIN_SCORE
    assert rank("workspace", [incidental], limit=4) == []


def test_ties_break_on_corpus_order_so_answers_are_reproducible() -> None:
    first = passage(title="Webhooks", heading="A")
    second = passage(title="Webhooks", heading="B")

    assert rank("webhooks", [first, second], limit=2) == [first, second]
    assert rank("webhooks", [second, first], limit=2) == [second, first]


def test_empty_query_matches_nothing() -> None:
    assert rank("   ", [passage(title="Webhooks")], limit=4) == []


@pytest.mark.parametrize(
    ("question", "expected_guide"),
    [
        ("How do I rotate an API key?", "/docs/platform/api-keys-and-sdks"),
        ("Where do I see why a run failed?", "/docs/observability/watch-a-run"),
        ("How do I publish a template to the marketplace?", "/docs/marketplace/publish-a-listing"),
        ("What roles can create agents?", "/docs/platform/roles-and-permissions"),
    ],
)
def test_real_questions_reach_the_right_guide(question: str, expected_guide: str) -> None:
    index = CorpusDocsIndex(load_passages())

    urls = {found.url.split("#")[0] for found in index.search(question, limit=4)}

    assert expected_guide in urls
