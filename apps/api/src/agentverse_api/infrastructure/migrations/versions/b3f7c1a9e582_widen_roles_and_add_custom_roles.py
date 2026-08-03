"""Widen the role model to seven tiers and add custom roles.

The enterprise spec requires seven built-in roles (owner, admin, manager,
developer, analyst, member, viewer) plus tenant-defined custom roles.

**Why `workspace_role` stops being a Postgres ENUM here.** Adding values
to a Postgres enum is easy; removing them is not — `ALTER TYPE ... DROP
VALUE` does not exist. An enum widened in place therefore has no working
`downgrade()`, which CLAUDE.md Rule 19 forbids. Converting the column to
TEXT with validation at the Pydantic/domain boundary makes the change
reversible and follows the precedent this codebase already set for
`api_keys.scope` and `sso_configurations.protocol`, both of which chose
TEXT for exactly this reason.

Validation does not weaken: `Role` is still a `StrEnum` parsed at every
boundary, so an invalid string is rejected before it reaches a query.
What is lost is a database-level constraint, so a CHECK constraint is
added to keep the guarantee where the enum had it — and unlike an enum,
a CHECK can be dropped and recreated freely.

**The downgrade demotes rather than escalates.** Reverting to the
four-value enum has to do something with rows holding one of the three
new roles. It maps them to `member`, the nearest strictly-lower legacy
tier. Mapping `manager` to `admin` would be the "closest" reading but
would silently grant billing and governance rights to people an operator
had deliberately kept below admin — a rollback must never widen access.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

#: `workspaces.id`/`roles.id` are UUID columns (`_uuid_pk`), while
#: `users.id` is TEXT (Better Auth owns its shape, ADR-0005). Foreign
#: keys must match the referenced type exactly or Postgres refuses the
#: constraint outright.
_UUID = postgresql.UUID(as_uuid=False)

revision = "b3f7c1a9e582"
down_revision = "a8c4d1f7b302"
branch_labels = None
depends_on = None

_LEGACY_ROLES = ("owner", "admin", "member", "viewer")
_ALL_ROLES = ("owner", "admin", "manager", "developer", "analyst", "member", "viewer")

#: Both tables carry the role and both must move together — they shared
#: the one enum type, so the type cannot be dropped while either remains.
_ROLE_TABLES = ("workspace_members", "organization_members")


def upgrade() -> None:
    for table in _ROLE_TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN role TYPE TEXT USING role::text")
        op.create_check_constraint(
            f"ck_{table}_role_valid",
            table,
            sa.column("role").in_(_ALL_ROLES),
        )

    # Only safe once no column references it.
    op.execute("DROP TYPE workspace_role")

    # Custom roles. Workspace-scoped rather than global: a role is a
    # tenant's own vocabulary, and a global role table would be a
    # cross-tenant surface on a `workspace_id`-absolute model (Rule 11).
    op.create_table(
        "roles",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "workspace_id",
            _UUID,
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # Every custom role inherits from a built-in tier. This is what
        # keeps `require_role`'s floor meaningful for a custom role: it
        # still has a rank, so pre-existing routes gated on a minimum
        # role keep working without knowing custom roles exist.
        sa.Column("base_role", sa.Text(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("base_role IN " + str(_ALL_ROLES), name="ck_roles_base_role_valid"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_role_workspace_name"),
    )
    op.create_index("ix_roles_workspace_id", "roles", ["workspace_id"])

    # Additive grants layered on the base role. No "deny" column by
    # design: a custom role that subtracts an inherited capability would
    # make the hierarchy non-monotonic and quietly break every route
    # still gated on a minimum role.
    op.create_table(
        "role_permissions",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "role_id",
            _UUID,
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("permission", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("role_id", "permission", name="uq_role_permission"),
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])

    # A member may hold a custom role instead of a built-in one. Nullable
    # so every pre-existing row is untouched and keeps using `role`.
    op.add_column(
        "workspace_members",
        sa.Column(
            "custom_role_id",
            _UUID,
            sa.ForeignKey("roles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_workspace_members_custom_role_id", "workspace_members", ["custom_role_id"])


def downgrade() -> None:
    op.drop_index("ix_workspace_members_custom_role_id", table_name="workspace_members")
    op.drop_column("workspace_members", "custom_role_id")
    op.drop_index("ix_role_permissions_role_id", table_name="role_permissions")
    op.drop_table("role_permissions")
    op.drop_index("ix_roles_workspace_id", table_name="roles")
    op.drop_table("roles")

    # Demote, never escalate — see the module docstring.
    for table in _ROLE_TABLES:
        op.execute(
            f"UPDATE {table} SET role = 'member' WHERE role IN ('manager', 'developer', 'analyst')"
        )
        op.drop_constraint(f"ck_{table}_role_valid", table, type_="check")

    sa.Enum(*_LEGACY_ROLES, name="workspace_role").create(op.get_bind())
    for table in _ROLE_TABLES:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN role TYPE workspace_role USING role::workspace_role"
        )
