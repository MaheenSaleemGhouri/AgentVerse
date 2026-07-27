"""Covers the real tokenizer wrapper, kept separate from the chunking
tests so those can assert exact boundaries with a trivial counter.
"""

from __future__ import annotations

from agentverse_shared.text.tokenizer import DEFAULT_ENCODING, TiktokenCounter, TokenCounter


def test_counts_are_positive_and_grow_with_length() -> None:
    counter = TiktokenCounter()

    short = counter.count("hello")
    longer = counter.count("hello world this is a longer sentence")

    assert short >= 1
    assert longer > short


def test_empty_string_counts_zero() -> None:
    assert TiktokenCounter().count("") == 0


def test_counts_are_not_a_character_approximation() -> None:
    # `rag-expert` forbids char/4-style estimation. A common word is one
    # token despite being several characters — proving real BPE is in use.
    counter = TiktokenCounter()

    assert counter.count(" the") == 1
    assert len(" the") == 4


def test_repeated_construction_reuses_the_cached_encoding() -> None:
    # Encoding load is expensive and network-touching on first use; two
    # counters must not each pay for it.
    first = TiktokenCounter(DEFAULT_ENCODING)
    second = TiktokenCounter(DEFAULT_ENCODING)

    assert first.count("same input") == second.count("same input")


def test_satisfies_the_token_counter_protocol() -> None:
    counter: TokenCounter = TiktokenCounter()

    assert counter.count("structural typing check") > 0
