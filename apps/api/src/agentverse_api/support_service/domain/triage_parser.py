"""Parses the `support-triage` marketplace template's structured-text
output (`marketplace_service/domain/templates.py`'s `support-triage`
system prompt: `category:`/`severity:`/`confidence:`/`draft_reply:`
lines) into typed fields.

Pure, zero I/O (CLAUDE.md §11) — never asserted against exact LLM output
text, only against the label/line shape a well-behaved completion of
this template produces. A completion that doesn't follow the format
(e.g. no `category:` line at all) parses to an all-`None` result rather
than raising — the caller decides that means the ticket's triage failed,
this function only ever describes what it found.

`priority` deliberately keeps the template's own vocabulary
(`urgent`/`high`/`normal`/`low`) rather than remapping it to some other
scale — inventing a second vocabulary here would be a second place that
could drift from what the template actually promises.
"""

from __future__ import annotations

from dataclasses import dataclass

_LABELS = ("category", "severity", "confidence", "draft_reply")


@dataclass(frozen=True, slots=True)
class TriageFields:
    category: str | None
    priority: str | None
    confidence: str | None
    draft_reply: str | None

    @property
    def is_complete(self) -> bool:
        """`category` is the one field a ticket cannot be usefully
        triaged without — `draft_reply` may legitimately be a
        clarifying question, and `confidence`/`priority` are advisory.
        """
        return self.category is not None


def parse_triage_output(text: str) -> TriageFields:
    values: dict[str, str] = {}
    current_label: str | None = None
    buffer: list[str] = []

    def _flush() -> None:
        if current_label is not None:
            values[current_label] = "\n".join(buffer).strip()

    for line in text.splitlines():
        stripped = line.strip()
        matched_label = next(
            (label for label in _LABELS if stripped.lower().startswith(f"{label}:")), None
        )
        if matched_label is not None:
            _flush()
            current_label = matched_label
            buffer = [stripped[len(matched_label) + 1 :].strip()]
        elif current_label is not None:
            buffer.append(line)
    _flush()

    return TriageFields(
        category=values.get("category") or None,
        priority=values.get("severity") or None,
        confidence=values.get("confidence") or None,
        draft_reply=values.get("draft_reply") or None,
    )
