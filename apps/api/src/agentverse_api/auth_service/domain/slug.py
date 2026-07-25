"""Pure slug generation — no I/O, unit-testable in isolation (CLAUDE.md §11)."""

from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    slug = _NON_ALNUM.sub("-", name.strip().lower()).strip("-")
    return slug or "workspace"


def candidate_slugs(name: str) -> list[str]:
    """Base slug first, then `-2`, `-3`, ... `-10` as fallback candidates
    for the caller to try against a uniqueness check.
    """
    base = slugify(name)
    return [base, *(f"{base}-{n}" for n in range(2, 11))]
