"""Shared SQLAlchemy result helpers.

Small, but genuinely shared: `affected()` was written once in the
knowledge repository and needed verbatim by the team repository. A second
copy would be duplication of exactly the kind Rule 3 rules out, and the
answer it computes is not cosmetic — it is what distinguishes "deleted"
from "no such row in this workspace", i.e. a 204 from a 404.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Result


def affected(result: Result[Any]) -> bool:
    """Whether a statement matched at least one row.

    `rowcount` is a `CursorResult` attribute while `execute()` is typed
    as returning the broader `Result`. Narrowed once here rather than
    with an inline type-ignore at every call site.
    """
    rowcount = getattr(result, "rowcount", None)
    return isinstance(rowcount, int) and rowcount > 0
