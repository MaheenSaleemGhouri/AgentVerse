"""Golden examples — the fixed input/expectation pairs a prompt version
is graded against (CLAUDE.md §9 "AI evaluation": golden datasets and
scoring rubrics are structured data, deterministic checks first,
LLM-as-judge only with a fixed reference-anchored rubric).

Pure — no I/O. Scoring itself lives in `eval_scoring.py`
(deterministic) and `application/eval_harness/llm_judge.py` (needs a
provider call, so it cannot be pure); this module only defines the
data shape a rubric scores against.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class RubricType(StrEnum):
    """How a golden example is graded, cheapest and most deterministic
    first — mirroring `rag-expert`'s "deterministic checks first, LLM-
    as-judge only where needed" ordering.
    """

    #: Output is `label: value` lines (the shape every structured-output
    #: first-party template already produces, e.g. support-triage's
    #: `category:`/`severity:`/...) — checked for required labels
    #: present and, optionally, values within an allowed set. Never an
    #: exact-text match (CLAUDE.md Rule 4).
    SCHEMA = "schema"
    #: Deterministic case-insensitive substring presence/absence checks
    #: against free-form prose output.
    KEYWORD = "keyword"
    #: A second model call, graded against a fixed reference answer and
    #: named criteria — reserved for prompts no structural or keyword
    #: check can meaningfully grade.
    LLM_JUDGE = "llm_judge"


@dataclass(frozen=True, slots=True)
class SchemaExpectation:
    """`RubricType.SCHEMA`'s expectation shape."""

    required_labels: tuple[str, ...]
    #: Optional per-label allow-list — e.g. `{"category": ("billing",
    #: "bug", ...)}`. A label present in `required_labels` but absent
    #: here is checked for presence only, not value.
    allowed_values: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class KeywordExpectation:
    """`RubricType.KEYWORD`'s expectation shape. Case-insensitive."""

    must_contain: tuple[str, ...] = ()
    must_not_contain: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LlmJudgeExpectation:
    """`RubricType.LLM_JUDGE`'s expectation shape — a reference answer
    plus the named criteria the judge model is instructed to check
    against it, never a bare "does this look good" prompt.
    """

    reference_answer: str
    criteria: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GoldenExample:
    """One fixed (input, expectation) pair a prompt version is run
    against during regression. `expectation`'s concrete type must match
    `rubric` — enforced by `eval_scoring`/`llm_judge` at scoring time,
    not by a discriminated union here, since the three expectation
    shapes above already make the mismatch a type error at every real
    call site.
    """

    id: str
    prompt_template_id: str
    #: Rendered into the user-turn message the prompt-under-test
    #: receives — e.g. `{"subject": "...", "body": "..."}` for
    #: support-triage, rendered by whichever caller knows that
    #: template's input shape (the harness itself stays input-shape
    #: agnostic; see `regression_runner.py`).
    input: dict[str, object]
    rubric: RubricType
    expectation: SchemaExpectation | KeywordExpectation | LlmJudgeExpectation
    created_at: datetime
