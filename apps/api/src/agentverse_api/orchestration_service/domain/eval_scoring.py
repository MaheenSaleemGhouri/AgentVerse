"""Deterministic scoring for `RubricType.SCHEMA`/`RubricType.KEYWORD`
golden examples (CLAUDE.md §9/§11: never an exact-text match against
non-deterministic LLM output — structure and behavior only).

Pure — no I/O, no provider call. `RubricType.LLM_JUDGE` is scored in
`application/eval_harness/llm_judge.py` instead, since grading against
a reference answer needs a second model call this module cannot make.

`parse_labeled_lines` generalizes `support_service/domain/
triage_parser.py`'s `label:`-line parsing (that module predates this
one and is left as its own small, already-tested parser rather than
rewritten to call this — see this module's own docstring note on why
duplicating a five-line loop was judged cheaper than coupling two
otherwise-unrelated domains together).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from agentverse_api.orchestration_service.domain.golden_dataset import (
    KeywordExpectation,
    SchemaExpectation,
)


@dataclass(frozen=True, slots=True)
class ExampleScore:
    """One golden example's grading result. `reason` is always populated
    — including on a pass — because "the failing eval results shown"
    acceptance criterion (docs/roadmap.md PHASE 8) needs somewhere to
    read *why*, not just a boolean.
    """

    passed: bool
    reason: str


def parse_labeled_lines(text: str, labels: Sequence[str]) -> dict[str, str]:
    """Splits `label: value` lines (case-insensitive label match,
    multi-line values folded into the label they followed) into a dict
    keyed by the *lowercased* label. A completion that doesn't follow
    the format parses to an empty dict rather than raising — the caller
    decides what an incomplete parse means for scoring.
    """
    values: dict[str, str] = {}
    current_label: str | None = None
    buffer: list[str] = []

    def _flush() -> None:
        if current_label is not None:
            values[current_label] = "\n".join(buffer).strip()

    lowered_labels = [label.lower() for label in labels]
    for line in text.splitlines():
        stripped = line.strip()
        matched = next(
            (label for label in lowered_labels if stripped.lower().startswith(f"{label}:")),
            None,
        )
        if matched is not None:
            _flush()
            current_label = matched
            buffer = [stripped[len(matched) + 1 :].strip()]
        elif current_label is not None:
            buffer.append(line)
    _flush()
    return values


def score_schema(output: str, expectation: SchemaExpectation) -> ExampleScore:
    """Passes when every required label is present and, for any label
    with an allow-list, its value is a member of that list. Value
    matching is case-insensitive — the model's exact casing is not the
    thing under test.
    """
    parsed = parse_labeled_lines(output, expectation.required_labels)
    missing = [label for label in expectation.required_labels if label.lower() not in parsed]
    if missing:
        return ExampleScore(
            passed=False, reason=f"missing required label(s): {', '.join(missing)}"
        )

    for label, allowed in expectation.allowed_values.items():
        value = parsed.get(label.lower(), "")
        allowed_lower = {v.lower() for v in allowed}
        if value.lower() not in allowed_lower:
            return ExampleScore(
                passed=False,
                reason=f"{label!r} was {value!r}, expected one of {', '.join(allowed)}",
            )

    return ExampleScore(passed=True, reason="all required labels present with allowed values")


def score_keyword(output: str, expectation: KeywordExpectation) -> ExampleScore:
    """Case-insensitive substring presence/absence — the cheapest
    deterministic check available for free-form prose output that has
    no `label:` structure to parse.
    """
    lowered = output.lower()
    missing = [kw for kw in expectation.must_contain if kw.lower() not in lowered]
    if missing:
        reason = f"missing required keyword(s): {', '.join(missing)}"
        return ExampleScore(passed=False, reason=reason)

    present = [kw for kw in expectation.must_not_contain if kw.lower() in lowered]
    if present:
        reason = f"contained forbidden keyword(s): {', '.join(present)}"
        return ExampleScore(passed=False, reason=reason)

    return ExampleScore(passed=True, reason="all keyword conditions satisfied")
