# RBAC matrix

The authoritative role/permission model. The source of truth is
`apps/api/src/agentverse_api/auth_service/domain/permission.py`; this
document explains it. If the two disagree, the code is right and this
file is a bug — `tests/auth_service/domain/test_permission_matrix.py`
asserts the properties described here.

## The two mechanisms, and why there are two

Authorization is decided by **two composable checks**, not one.

| | `require_role(minimum)` | `require_permission(permission)` |
|---|---|---|
| Asks | "is this member at least an admin?" | "may this member delete an agent?" |
| Backed by | a linear rank | a role × permission table |
| Used for | coarse floors on whole route groups | specific capabilities |

A single mechanism cannot express the model. A linear rank alone cannot
say that an **analyst** and a **developer** are both "above member" but
are not comparable to each other — one reads billing, the other deletes
agents, and neither is a superset of the other in intent. A permission
table alone cannot express "everything under this router needs at least
admin" without restating the same set on every route.

So they compose. `require_permission` is layered *alongside*
`require_role`, never in place of it (ADR-0004). Every route that
existed before permissions shipped is byte-for-byte unaffected.

## Built-in roles

Seven tiers, strictly ordered by rank:

```
owner (6) > admin (5) > manager (4) > developer (3) > analyst (2) > member (1) > viewer (0)
```

The three tiers added in Phase 8 — manager, developer, analyst — were
inserted **between admin and member**. That placement is the reason the
change is additive rather than breaking:

- `require_role(ADMIN)` still admits exactly `owner` and `admin`. No
  existing call site silently widened.
- `require_role(MEMBER)` now also admits `manager`, `developer` and
  `analyst`, which is the intended reading — they are all above member.

`LEGACY_ROLES` names the original four so tests can assert the old set
still behaves identically.

## Permission inheritance

Each tier's grants are **cumulative**: a tier holds its own grants plus
every grant of every tier below it. This is computed once at import
(`_resolve_inherited`), not hand-maintained per row, so the superset
property cannot drift.

| Tier | Adds on top of the tier below |
|---|---|
| `viewer` | every `*:view` read |
| `member` | run agents; create and edit agents, teams, knowledge |
| `analyst` | `analytics:view`, `audit:view`, `billing:view` |
| `developer` | deletes (agent, team, knowledge); MCP management; API keys |
| `manager` | member management (`invite`, `remove`, `assign_role`), workspace settings |
| `admin` | `billing:manage` |
| `owner` | nothing new — see below |

**Why `owner` adds no permissions.** Ownership is enforced
*structurally*, not by a permission bit: the last owner cannot be
removed or demoted (`LastOwnerError`), and ownership transfer is its own
atomic operation. Modelling "delete the workspace" as a grant would make
it delegable, which is exactly what ownership must not be.

## Custom roles

A workspace may define its own roles (`roles` / `role_permissions`).

A custom role is **a base tier plus extra grants — never fewer**. It
cannot subtract. That is a deliberate constraint, not a missing feature:

- The whole `require_role` floor depends on rank being monotonic. If a
  custom role anchored at `admin` could deny `agent:view`, then "at
  least admin" would stop implying "can do everything a viewer can", and
  every existing floor check silently becomes untrue.
- Deny rules also make effective permissions order-dependent and hard to
  reason about at a glance, which is the opposite of what an access
  model is for.

Grants already inherited from the base tier are **not stored** on the
custom role. Storing them would freeze a copy of the base tier's matrix
at creation time, so a later change to what `developer` can do would
silently not reach custom roles built on it.

Deleting a custom role does not lock anyone out: holders fall back to
their base tier.

## Storage

Role columns are `TEXT` with a `CHECK`, not a Postgres `ENUM`.

Postgres has no `ALTER TYPE ... DROP VALUE`. An enum-backed role column
can be extended but never cleanly rolled back, which fails this repo's
additive-and-reversible migration standard (Rule 19). `api_keys.scope`
and `sso_configurations.protocol` already set this precedent; migration
`b3f7c1a9e582` moved the role columns onto it.

A `RoleType` `TypeDecorator` maps the column to the `Role` enum in
Python, so `Mapped[Role]` stays true. Without it SQLAlchemy returns bare
strings and `role is Role.OWNER` fails while `role == Role.OWNER` keeps
working — a failure mode that survives a casual test suite.

The **downgrade demotes** `manager`/`developer`/`analyst` to `member`.
A rollback must never widen anyone's access, and promoting them to
`admin` to "preserve seniority" would do exactly that. This is asserted
against real Postgres.

## Organization roles

Organizations reuse the same `Role` values with the same ordering, and
`require_org_role` mirrors `require_role` exactly.

They are **separate authorization domains**. Organization membership
grants zero workspace access (ADR-0011). An organization owner with no
`workspace_members` row has no access to any of that organization's
workspaces, and there is no code path that grants it.

## Denials

Every denial is written to `audit_logs` from the enforcement point, so
it cannot be bypassed by a route author who forgets to log:
`permission.denied` (role floor), `resource_permission.denied`,
`org_permission.denied`.

Cross-workspace access returns **404, not 403** — a workspace's
existence is not disclosed to someone outside it. Within a workspace, an
insufficient role returns 403, because the resource's existence is
already known to the caller.
