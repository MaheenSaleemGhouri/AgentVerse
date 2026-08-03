"""The canonical permission matrix: role x action x resource, in one place.

`authorization-expert` requires a single canonical location for this
table so route-level checks are derived from it rather than hand-written
per route — a hand-written check is where a typo silently becomes an
unenforced permission.

**How this composes with `role.py`.** `satisfies()` answers "is this role
at least X" and remains the floor every existing route is built on. This
module answers the narrower question "may this role do Y to resource Z".
Both are needed: a total order keeps `require_role` coherent, but a
total order alone cannot express that an `analyst` reads analytics while
a `developer` builds agents, and neither outranks the other on the
other's ground.

**Inheritance.** A role's grant set is its own row unioned with every
lower-ranked role's row (`_resolve_inherited`). That is what makes the
hierarchy a documented superset rather than seven independent lists that
drift — adding a permission to `viewer` correctly grants it to all seven
roles, and there is no way to accidentally give a `member` something a
`manager` lacks.

**Custom roles** (`rbac_service`) layer on top: they inherit from a
built-in base role and add grants. They can never subtract, because a
role that silently removes an inherited capability would make the
hierarchy non-monotonic and break the `require_role` floor that every
pre-existing route still depends on.
"""

from __future__ import annotations

from enum import StrEnum

from agentverse_api.auth_service.domain.role import Role


class Permission(StrEnum):
    """`<resource>:<action>`, covering the resources CLAUDE.md §5 names.

    Typed rather than free-form strings so a misspelled permission is a
    static error at the call site instead of a check that silently never
    matches.
    """

    # Agents
    AGENT_VIEW = "agent:view"
    AGENT_CREATE = "agent:create"
    AGENT_EDIT = "agent:edit"
    AGENT_DELETE = "agent:delete"
    AGENT_RUN = "agent:run"

    # Teams (multi-agent)
    TEAM_VIEW = "team:view"
    TEAM_CREATE = "team:create"
    TEAM_EDIT = "team:edit"
    TEAM_DELETE = "team:delete"

    # Knowledge bases
    KNOWLEDGE_VIEW = "knowledge:view"
    KNOWLEDGE_CREATE = "knowledge:create"
    KNOWLEDGE_EDIT = "knowledge:edit"
    KNOWLEDGE_DELETE = "knowledge:delete"

    # MCP integrations
    MCP_VIEW = "mcp:view"
    MCP_INSTALL = "mcp:install"
    MCP_EDIT = "mcp:edit"
    MCP_DELETE = "mcp:delete"

    # Billing
    BILLING_VIEW = "billing:view"
    BILLING_MANAGE = "billing:manage"

    # Workspace / organization settings
    SETTINGS_VIEW = "settings:view"
    SETTINGS_MANAGE = "settings:manage"

    # API keys
    API_KEY_VIEW = "api_key:view"
    API_KEY_CREATE = "api_key:create"
    API_KEY_ROTATE = "api_key:rotate"
    API_KEY_REVOKE = "api_key:revoke"

    # Analytics
    ANALYTICS_VIEW = "analytics:view"
    ANALYTICS_EXPORT = "analytics:export"

    # Audit logs
    AUDIT_LOG_VIEW = "audit_log:view"
    AUDIT_LOG_EXPORT = "audit_log:export"

    # Membership administration
    MEMBER_VIEW = "member:view"
    MEMBER_INVITE = "member:invite"
    MEMBER_REMOVE = "member:remove"
    MEMBER_ASSIGN_ROLE = "member:assign_role"


#: Each role's *own* grants. Read this together with `_resolve_inherited`:
#: the effective set is this row plus every lower-ranked role's row, so a
#: row lists only what that tier adds on top of the tier beneath it.
#:
#: The shape of the ladder:
#: - `viewer` reads the product surfaces but nothing governance-related.
#: - `member` additionally runs agents and creates/edits their own work.
#: - `analyst` adds the reporting surfaces (analytics, audit read/export)
#:   without gaining any authoring power — the read-heavy compliance seat.
#: - `developer` adds authoring depth (delete agents/teams/KBs, install
#:   and configure MCP, manage API keys) without governance.
#: - `manager` adds people management and settings, but not billing.
#: - `admin` adds billing and full governance.
#: - `owner` adds nothing new here; its distinction is ownership transfer
#:   and workspace deletion, which are guarded structurally rather than
#:   by a permission flag (see `workspace_service`), because "last owner"
#:   is a cardinality rule, not a capability.
_OWN_GRANTS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset(
        {
            Permission.AGENT_VIEW,
            Permission.TEAM_VIEW,
            Permission.KNOWLEDGE_VIEW,
            Permission.MCP_VIEW,
            Permission.SETTINGS_VIEW,
            Permission.MEMBER_VIEW,
        }
    ),
    Role.MEMBER: frozenset(
        {
            Permission.AGENT_CREATE,
            Permission.AGENT_EDIT,
            Permission.AGENT_RUN,
            Permission.TEAM_CREATE,
            Permission.TEAM_EDIT,
            Permission.KNOWLEDGE_CREATE,
            Permission.KNOWLEDGE_EDIT,
        }
    ),
    Role.ANALYST: frozenset(
        {
            Permission.ANALYTICS_VIEW,
            Permission.ANALYTICS_EXPORT,
            Permission.AUDIT_LOG_VIEW,
            Permission.AUDIT_LOG_EXPORT,
            Permission.BILLING_VIEW,
        }
    ),
    Role.DEVELOPER: frozenset(
        {
            Permission.AGENT_DELETE,
            Permission.TEAM_DELETE,
            Permission.KNOWLEDGE_DELETE,
            Permission.MCP_INSTALL,
            Permission.MCP_EDIT,
            Permission.MCP_DELETE,
            Permission.API_KEY_VIEW,
            Permission.API_KEY_CREATE,
            Permission.API_KEY_ROTATE,
            Permission.API_KEY_REVOKE,
        }
    ),
    Role.MANAGER: frozenset(
        {
            Permission.MEMBER_INVITE,
            Permission.MEMBER_REMOVE,
            Permission.MEMBER_ASSIGN_ROLE,
            Permission.SETTINGS_MANAGE,
        }
    ),
    Role.ADMIN: frozenset({Permission.BILLING_MANAGE}),
    Role.OWNER: frozenset(),
}


def _resolve_inherited() -> dict[Role, frozenset[Permission]]:
    """Unions each role's own grants with every lower-ranked role's.

    Computed once at import rather than per check: the matrix is static,
    and resolving it on every request would put a loop over seven roles
    inside the hot authorization path for no benefit.
    """
    from agentverse_api.auth_service.domain.role import rank

    ordered = sorted(Role, key=rank)
    resolved: dict[Role, frozenset[Permission]] = {}
    accumulated: frozenset[Permission] = frozenset()
    for role in ordered:
        accumulated = accumulated | _OWN_GRANTS[role]
        resolved[role] = accumulated
    return resolved


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = _resolve_inherited()


def permissions_for(role: Role) -> frozenset[Permission]:
    """Every permission `role` holds, inherited grants included."""
    return ROLE_PERMISSIONS[role]


def has_permission(role: Role, permission: Permission) -> bool:
    """Whether `role` may perform `permission`.

    Pure and side-effect free so it is unit-testable without HTTP or a
    database, per `authorization-expert`'s coding standard — the FastAPI
    dependency that calls it holds all the I/O.
    """
    return permission in ROLE_PERMISSIONS[role]
