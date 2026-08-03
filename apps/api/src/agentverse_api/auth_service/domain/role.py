"""Workspace role hierarchy (CLAUDE.md §10).

`owner > admin > manager > developer > analyst > member > viewer`.

A plain `str` enum so it serializes cleanly to/from Postgres and JSON
without a translation layer, while `_RANK` gives it the ordering a bare
string enum doesn't have for free.

**Why the three middle roles slot between `admin` and `member`, and why
that is backward-compatible.** The original four were
`owner > admin > member > viewer`; `manager`, `developer` and `analyst`
were inserted into the middle of that order rather than appended, so
every pre-existing comparison keeps its exact meaning:

- `require_role(Role.ADMIN)` still admits only `owner`/`admin` — the new
  roles rank below `admin`, so nothing gained admin power silently.
- `require_role(Role.MEMBER)` now also admits `manager`/`developer`/
  `analyst`, which is the intended reading: all three are strictly more
  privileged than a plain member.
- `owner`/`admin`/`member`/`viewer` keep their relative order, so no
  existing route changed behaviour for any existing member row.

The ranks themselves are renumbered (`admin` moved from 2 to 5), which
is safe because rank is an in-process ordering detail — it is never
persisted, serialized, or compared across processes. Only the string
values reach the database.

Linear rank answers "is this role at least X". It deliberately does not
answer "may this role do Y to resource Z" — that is
`permission.py`'s matrix, because `analyst` and `developer` are not
meaningfully ordered against each other on every action even though a
total order is required for the `require_role` floor to stay coherent.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    DEVELOPER = "developer"
    ANALYST = "analyst"
    MEMBER = "member"
    VIEWER = "viewer"


#: The four roles that existed before the enterprise RBAC extension.
#: Kept explicit so migrations and tests can assert that the original
#: semantics are untouched rather than re-deriving the set by hand.
LEGACY_ROLES: frozenset[Role] = frozenset({Role.OWNER, Role.ADMIN, Role.MEMBER, Role.VIEWER})

_RANK: dict[Role, int] = {
    Role.OWNER: 6,
    Role.ADMIN: 5,
    Role.MANAGER: 4,
    Role.DEVELOPER: 3,
    Role.ANALYST: 2,
    Role.MEMBER: 1,
    Role.VIEWER: 0,
}


def satisfies(actual: Role, minimum: Role) -> bool:
    """True if `actual` is at least as privileged as `minimum`."""
    return _RANK[actual] >= _RANK[minimum]


def rank(role: Role) -> int:
    """The role's position in the hierarchy; higher is more privileged.

    Exposed so callers (ownership transfer, role-assignment guards) can
    compare two roles without importing the private table or
    re-implementing the ordering.
    """
    return _RANK[role]
