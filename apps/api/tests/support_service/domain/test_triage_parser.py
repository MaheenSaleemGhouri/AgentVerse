"""Pure-function tests — zero I/O, no exact-LLM-text assertions beyond
the label/line shape itself (CLAUDE.md §11)."""

from __future__ import annotations

from agentverse_api.support_service.domain.triage_parser import parse_triage_output


def test_parses_all_four_labelled_fields() -> None:
    text = (
        "category: billing\n"
        "severity: high\n"
        "confidence: high\n"
        "draft_reply: Thanks for reaching out, we're looking into this."
    )
    fields = parse_triage_output(text)
    assert fields.category == "billing"
    assert fields.priority == "high"
    assert fields.confidence == "high"
    assert fields.draft_reply == "Thanks for reaching out, we're looking into this."
    assert fields.is_complete


def test_draft_reply_spans_multiple_lines_to_end_of_text() -> None:
    text = "category: bug\nseverity: normal\nconfidence: low\ndraft_reply: Line one.\nLine two."
    fields = parse_triage_output(text)
    assert fields.draft_reply == "Line one.\nLine two."


def test_labels_are_case_insensitive() -> None:
    text = "Category: how-to\nSeverity: low\nConfidence: high\nDraft_Reply: See the docs."
    fields = parse_triage_output(text)
    assert fields.category == "how-to"
    assert fields.draft_reply == "See the docs."


def test_missing_category_is_incomplete() -> None:
    text = "severity: high\nconfidence: high\ndraft_reply: We'll look into it."
    fields = parse_triage_output(text)
    assert fields.category is None
    assert not fields.is_complete


def test_completely_unstructured_text_parses_to_all_none() -> None:
    fields = parse_triage_output("I'm not sure how to help with this one.")
    assert fields == parse_triage_output("")
    assert not fields.is_complete


def test_extra_prose_before_the_first_label_is_ignored() -> None:
    text = (
        "Sure, here's my analysis:\n\n"
        "category: account\nseverity: low\nconfidence: high\ndraft_reply: Okay."
    )
    fields = parse_triage_output(text)
    assert fields.category == "account"
