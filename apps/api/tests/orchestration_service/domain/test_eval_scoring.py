"""Unit tests for `domain.eval_scoring`'s deterministic rubrics — pure,
zero I/O, no LLM call (CLAUDE.md §11).
"""

from __future__ import annotations

from agentverse_api.orchestration_service.domain.eval_scoring import (
    parse_labeled_lines,
    score_keyword,
    score_schema,
)
from agentverse_api.orchestration_service.domain.golden_dataset import (
    KeywordExpectation,
    SchemaExpectation,
)


class TestParseLabeledLines:
    def test_extracts_single_line_values(self) -> None:
        text = "category: billing\nseverity: urgent"
        parsed = parse_labeled_lines(text, ["category", "severity"])
        assert parsed == {"category": "billing", "severity": "urgent"}

    def test_folds_multi_line_values_into_the_preceding_label(self) -> None:
        text = "draft_reply: Thanks for reaching out.\nWe will look into this."
        parsed = parse_labeled_lines(text, ["draft_reply"])
        assert parsed["draft_reply"] == "Thanks for reaching out.\nWe will look into this."

    def test_label_matching_is_case_insensitive(self) -> None:
        parsed = parse_labeled_lines("Category: bug", ["category"])
        assert parsed == {"category": "bug"}

    def test_a_completion_with_no_labels_parses_to_an_empty_dict(self) -> None:
        assert parse_labeled_lines("just some prose", ["category"]) == {}


class TestScoreSchema:
    def test_passes_when_every_required_label_is_present(self) -> None:
        output = "category: billing\nseverity: urgent\nconfidence: high\ndraft_reply: Sorry!"
        expectation = SchemaExpectation(
            required_labels=("category", "severity", "confidence", "draft_reply")
        )
        result = score_schema(output, expectation)
        assert result.passed is True

    def test_fails_and_names_the_missing_label(self) -> None:
        output = "category: billing"
        expectation = SchemaExpectation(required_labels=("category", "severity"))
        result = score_schema(output, expectation)
        assert result.passed is False
        assert "severity" in result.reason

    def test_fails_when_a_value_is_outside_its_allowed_set(self) -> None:
        output = "category: made-up-category"
        expectation = SchemaExpectation(
            required_labels=("category",), allowed_values={"category": ("billing", "bug")}
        )
        result = score_schema(output, expectation)
        assert result.passed is False
        assert "made-up-category" in result.reason

    def test_allowed_value_matching_is_case_insensitive(self) -> None:
        output = "severity: URGENT"
        expectation = SchemaExpectation(
            required_labels=("severity",), allowed_values={"severity": ("urgent", "high")}
        )
        result = score_schema(output, expectation)
        assert result.passed is True

    def test_never_an_exact_text_match_extra_whitespace_and_casing_still_pass(self) -> None:
        # CLAUDE.md Rule 4: structural, not exact-string, assertions
        # against non-deterministic LLM output.
        output = "Category:   Billing  \nseverity: urgent"
        expectation = SchemaExpectation(required_labels=("category", "severity"))
        result = score_schema(output, expectation)
        assert result.passed is True


class TestScoreKeyword:
    def test_passes_when_every_required_keyword_is_present(self) -> None:
        result = score_keyword(
            "We support Slack and Notion integrations.",
            KeywordExpectation(must_contain=("Slack", "Notion")),
        )
        assert result.passed is True

    def test_keyword_matching_is_case_insensitive(self) -> None:
        result = score_keyword("we support SLACK.", KeywordExpectation(must_contain=("Slack",)))
        assert result.passed is True

    def test_fails_and_names_the_missing_keyword(self) -> None:
        result = score_keyword("We support Slack.", KeywordExpectation(must_contain=("Notion",)))
        assert result.passed is False
        assert "Notion" in result.reason

    def test_fails_on_a_forbidden_keyword(self) -> None:
        result = score_keyword(
            "This is a revolutionary new tool.",
            KeywordExpectation(must_not_contain=("revolutionary",)),
        )
        assert result.passed is False
        assert "revolutionary" in result.reason

    def test_passes_with_no_expectations_at_all(self) -> None:
        result = score_keyword("anything goes", KeywordExpectation())
        assert result.passed is True
