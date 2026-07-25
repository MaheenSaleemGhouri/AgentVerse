"""Workspace role hierarchy: owner > admin > member > viewer (CLAUDE.md §10).

A plain `str` enum so it serializes cleanly to/from Postgres and JSON
without a translation layer, while `_RANK` gives it the ordering a bare
string enum doesn't have for free.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


_RANK: dict[Role, int] = {
    Role.OWNER: 3,
    Role.ADMIN: 2,
    Role.MEMBER: 1,
    Role.VIEWER: 0,
}


def satisfies(actual: Role, minimum: Role) -> bool:
    """True if `actual` is at least as privileged as `minimum`."""
    return _RANK[actual] >= _RANK[minimum]
