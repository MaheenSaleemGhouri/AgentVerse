"""The translation from what a user typed to a Postgres `tsquery`.

Pure, so it is tested pure. The security-relevant property here is that
`to_tsquery` — unlike `plainto_tsquery` — parses its argument as an
expression, so anything that reaches it is executable syntax. These
tests pin that nothing but alphanumerics and `:*` ever does.
"""

from __future__ import annotations

import pytest

from agentverse_shared.search import (
    MAX_QUERY_LENGTH,
    MAX_TERMS,
    MIN_QUERY_LENGTH,
    SearchMatch,
    is_searchable,
    to_prefix_tsquery,
)


class TestNormalization:
    def test_a_single_word_becomes_a_prefix_term(self) -> None:
        assert to_prefix_tsquery("sales") == "sales:*"

    def test_words_are_anded_so_each_keystroke_narrows(self) -> None:
        assert to_prefix_tsquery("sales qualifier") == "sales:* & qualifier:*"

    def test_every_term_is_a_prefix_not_just_the_last(self) -> None:
        # This is what makes it a typeahead: someone mid-word in *any*
        # position still matches. `websearch_to_tsquery` would look for
        # the literal word "qual" and find nothing.
        assert to_prefix_tsquery("sal qual") == "sal:* & qual:*"

    def test_case_is_folded(self) -> None:
        assert to_prefix_tsquery("SaLeS") == "sales:*"

    def test_digits_survive(self) -> None:
        assert to_prefix_tsquery("gpt 4o") == "gpt:* & 4o:*"


class TestInjectionSafety:
    @pytest.mark.parametrize(
        "raw",
        [
            "sales & !qualifier",
            "sales | qualifier",
            "sales <-> qualifier",
            "'sales'",
            "(sales)",
            "sales:*:*",
            "sales'; DROP TABLE agents; --",
        ],
    )
    def test_no_tsquery_operator_survives(self, raw: str) -> None:
        result = to_prefix_tsquery(raw)
        assert result is not None
        # Only the operators this function itself emits may appear.
        for forbidden in ("!", "|", "<->", "'", "(", ")", ";", "-"):
            assert forbidden not in result

    def test_the_dangerous_input_still_searches_for_its_words(self) -> None:
        # Sanitizing must not mean discarding: the user typed real words
        # alongside the punctuation and should get results for them.
        assert to_prefix_tsquery("sales'; DROP TABLE agents; --") == (
            "sales:* & drop:* & table:* & agents:*"
        )

    @pytest.mark.parametrize("raw", ["", "   ", "!!!", "&|()", "…—"])
    def test_nothing_worth_querying_returns_none(self, raw: str) -> None:
        # `None` rather than an empty string: an empty `tsquery` is a
        # syntax error in Postgres, so the caller must be forced to
        # notice rather than pass it through.
        assert to_prefix_tsquery(raw) is None


class TestCaps:
    def test_term_count_is_capped(self) -> None:
        raw = " ".join(f"term{index}" for index in range(MAX_TERMS + 10))
        result = to_prefix_tsquery(raw)
        assert result is not None
        assert result.count("&") == MAX_TERMS - 1

    def test_a_long_paste_is_truncated_not_rejected(self) -> None:
        # Degrading to "search the first words" beats refusing, because
        # refusing puts an error under the search box.
        raw = "alpha " + ("x" * MAX_QUERY_LENGTH)
        result = to_prefix_tsquery(raw)
        assert result is not None
        assert result.startswith("alpha:*")
        # The truncation is of the *input*, so the surviving second term
        # is only what fitted inside `MAX_QUERY_LENGTH` — the six
        # characters of "alpha " having already been spent. (The output
        # can still be longer than the input, since every term grows by
        # the two characters of `:*`.)
        second_term = result.split(" & ")[1].removesuffix(":*")
        assert len(second_term) == MAX_QUERY_LENGTH - len("alpha ")


class TestIsSearchable:
    def test_below_the_minimum_is_not_searchable(self) -> None:
        assert not is_searchable("a")

    def test_at_the_minimum_is_searchable(self) -> None:
        assert is_searchable("a" * MIN_QUERY_LENGTH)

    def test_punctuation_of_sufficient_length_is_still_not_searchable(self) -> None:
        # Long enough to pass the length check, but normalizes to
        # nothing — both conditions have to hold.
        assert not is_searchable("!!!!!!")

    def test_whitespace_does_not_count_toward_the_minimum(self) -> None:
        assert not is_searchable("  a  ")


def test_search_match_is_immutable() -> None:
    match = SearchMatch(id="a1", title="Sales qualifier", subtitle=None, rank=0.5)
    with pytest.raises(AttributeError):
        match.title = "something else"  # type: ignore[misc]
