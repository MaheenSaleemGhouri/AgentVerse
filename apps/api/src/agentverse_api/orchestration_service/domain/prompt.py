"""Prompt templates and versions (Phase 8, docs/roadmap.md "PHASE 8").

**A prompt is a versioned artifact, never an inline string literal.**
Before this module, every first-party prompt AgentVerse ships (the 11
marketplace starter templates' `system_instructions`,
`marketplace_service/domain/templates.py`) lived as a Python string
constant with no version history and no eval gate — exactly the pattern
CLAUDE.md §4 forbids ("no prompt ships or changes without an eval run").
This module is the registry those prompts (and any future first-party/
internal prompt) are versioned and eval-gated through.

Pure — no I/O, no framework. Mirrors `domain/listing.py`'s shape
deliberately: a template is the stable identity (`slug`), a version is
an immutable snapshot once it ships, and the transition rules are a
small closed table exactly like `listing.py`'s `_TRANSITIONS`.

**Why versions are immutable once `ACTIVE`.** A version's
`system_instructions`/`model` are what its eval run actually tested —
editing them in place after promotion would silently invalidate the
recorded pass without anyone noticing. Changing a prompt means
authoring a new `DRAFT` version and running the gate again, the same
discipline `listing.py`'s "a listing version is an immutable snapshot"
comment states for marketplace installs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class PromptVersionStatus(StrEnum):
    """Where a version is in its lifecycle.

    `DRAFT` is where every version starts and where its
    `system_instructions`/`model` may still be edited. `ACTIVE` is the
    one version a template's real callers resolve to
    (`get_active_version`) — promotion is guarded by
    `promote_prompt_version`'s eval gate, never set directly. `ARCHIVED`
    is a version a newer one has superseded; it is retained, never
    deleted, so version history stays inspectable.
    """

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


_TRANSITIONS: dict[tuple[PromptVersionStatus, PromptVersionStatus], bool] = {
    (PromptVersionStatus.DRAFT, PromptVersionStatus.ACTIVE): True,
    # Abandoning a draft that turned out not to be worth shipping.
    (PromptVersionStatus.DRAFT, PromptVersionStatus.ARCHIVED): True,
    # A newer version supersedes this one.
    (PromptVersionStatus.ACTIVE, PromptVersionStatus.ARCHIVED): True,
}


class PromptVersionNotFoundError(Exception):
    """Maps to HTTP 404. The one definition every caller (the eval
    harness, the promotion gate, the admin routes) imports — CLAUDE.md
    Rule 3, DRY: two independently-defined "this id doesn't exist"
    exceptions for the same entity is exactly the duplication that
    drifts the first time one gains a field the other doesn't.
    """

    def __init__(self, version_id: str) -> None:
        self.version_id = version_id
        super().__init__(f"Prompt version {version_id!r} does not exist")


class InvalidPromptVersionTransitionError(Exception):
    """Maps to HTTP 409 — well-formed request, wrong current state."""

    def __init__(self, *, current: PromptVersionStatus, target: PromptVersionStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Cannot move a prompt version from {current.value!r} to {target.value!r}")


def can_transition(*, current: PromptVersionStatus, target: PromptVersionStatus) -> bool:
    return _TRANSITIONS.get((current, target), False)


def assert_transition(*, current: PromptVersionStatus, target: PromptVersionStatus) -> None:
    if not can_transition(current=current, target=target):
        raise InvalidPromptVersionTransitionError(current=current, target=target)


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """The stable identity a prompt's versions are grouped under.

    Not workspace-owned: first-party prompts are platform content
    (`marketplace_service/domain/templates.py`'s own precedent — the
    `PLATFORM_WORKSPACE_ID` fixed publisher, curated by a reviewed
    migration, not by a route any customer can reach), the same
    reasoning applied here one level up, at the prompt-authoring layer
    a marketplace listing's `system_instructions` is drawn from.
    """

    id: str
    slug: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PromptVersion:
    """One immutable-once-active snapshot of a template's prompt text.

    `version_number` is 1-indexed per template, matching
    `AgentVersion.version_number`'s convention exactly.
    """

    id: str
    prompt_template_id: str
    version_number: int
    system_instructions: str
    model: str
    temperature: float | None
    status: PromptVersionStatus
    created_at: datetime
    activated_at: datetime | None
