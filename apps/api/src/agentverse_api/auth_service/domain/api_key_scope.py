"""API key scope, and how it composes with the issuing member's role.

A key never grants more than the member who issued it holds: the
effective role of a request authenticated by an API key is the
*intersection* of the key's scope and that member's current workspace
role (CLAUDE.md §7/§10). So a `read_only` key issued by an owner is
capped at viewer, and a `full` key issued by a member is capped at
member — and demoting that member immediately narrows every key they
issued, without touching the keys themselves.
"""

from __future__ import annotations

from enum import StrEnum

from agentverse_api.auth_service.domain.role import Role, satisfies


class ApiKeyScope(StrEnum):
    FULL = "full"
    READ_ONLY = "read_only"


#: The highest role each scope will ever yield, regardless of how
#: privileged the issuing member is.
_SCOPE_CEILING: dict[ApiKeyScope, Role] = {
    ApiKeyScope.FULL: Role.OWNER,
    ApiKeyScope.READ_ONLY: Role.VIEWER,
}


def effective_role(scope: ApiKeyScope, member_role: Role) -> Role:
    """The role a request bearing this key actually acts with.

    Pure and total, so `require_role`'s existing hierarchy applies to
    key-authenticated requests without a second, parallel permission
    model to keep in sync (CLAUDE.md §3: testability).
    """
    ceiling = _SCOPE_CEILING[scope]
    return ceiling if satisfies(member_role, ceiling) else member_role
