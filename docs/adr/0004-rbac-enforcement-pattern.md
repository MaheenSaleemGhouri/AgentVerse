# ADR-0004: RBAC Enforcement Pattern

## Context

`CLAUDE.md` Rule 11 makes `workspace_id` tenant isolation absolute: "every tenant-owned table, every query, every cache key... carries and filters by `workspace_id`; cross-workspace access is denied without leaking existence." `CLAUDE.md` §10 requires deny-by-default RBAC via "the single shared permission-check dependency," `403` for same-workspace permission gaps and `404` for cross-workspace resources. `docs/roadmap.md` Phase 1's biggest named risk is getting `403` vs. `404` wrong on a single-workspace test fixture that never exercises the cross-tenant path. This ADR fixes the exact mechanics before any route depends on them, so every route added from Phase 1 onward composes the same two dependencies instead of each author re-deriving the pattern.

## Decision

**Two composable FastAPI dependencies, always used together, never one without the other:**

1. **`get_current_identity`** — verifies the request's Better Auth-issued JWT (see ADR-0005) against Better Auth's JWKS endpoint and returns the verified `user_id` (the token's `sub` claim). This is the *only* place `user_id` is trusted from — never a body/query param.

2. **`get_current_workspace(workspace_id: str = Path(...), identity = Depends(get_current_identity))`** — takes the `workspace_id` **path** parameter (required by `CLAUDE.md`'s own REST convention, `/v1/workspaces/{workspace_id}/...`) and the verified identity, then runs exactly one query: `SELECT role FROM workspace_members WHERE workspace_id = :workspace_id AND user_id = :user_id`. No row → raise `404` (workspace not found, from this user's point of view — existence is not leaked to a non-member). A row exists → return a `WorkspaceContext(workspace_id, user_id, role)`.

   This is the resolution of the "never client-supplied" requirement: the `workspace_id` string *does* originate in the URL (unavoidable, and correct, per REST convention) — the invariant is that it is **never used to authorize anything without this membership lookup keyed by the JWT-verified `user_id`.** A forged/guessed `workspace_id` a user isn't a member of always resolves to `404`, never to real data.

3. **`require_role(minimum: Role)`** — a dependency factory. `require_role(Role.ADMIN)` returns a dependency that takes the `WorkspaceContext` from `get_current_workspace`, compares the member's role against the ordered hierarchy `owner > admin > member > viewer`, and raises `403` (with an `audit_logs` write recording the denial) if the member's role is below `minimum`. Every route handler that mutates or reads sensitive workspace-scoped state depends on `require_role(...)`, never on a hand-rolled `if role != "owner"` check inline in the handler.

**Stubbed for future resource types, kept minimal.** `require_role` checks only the *workspace-level* role in Phase 1 — there is no per-resource permission table yet (no agents, knowledge bases, or billing exist to scope permissions on). Its signature (`minimum: Role`, resolved from `WorkspaceContext`) is deliberately resource-type-agnostic so Phase 4+ can add a second, resource-scoped check *alongside* it without changing this dependency's contract — this ADR does not guess what that future shape looks like (`docs/roadmap.md` Phase 1's own stated risk).

**Audit logging happens at the enforcement point, not the call site.** Both a granted sensitive action (e.g. a role change) and a denied one write to `audit_logs` from inside `require_role`/the use case that performs the mutation — never left to individual route handlers to remember, which is how audit coverage gaps happen in practice.

## Consequences

**Positive:** every route's tenant-isolation and permission behavior is identical by construction (two dependencies, composed the same way every time) rather than re-derived per route; the `403`-vs-`404` distinction is enforced in exactly one place, closing this phase's named top risk; audit-log coverage for grants/denials can't be silently skipped because it lives inside the shared dependency, not the caller.

**Negative:** a route author who forgets to depend on `require_role` entirely (not gets it wrong, but omits it) is not caught by this pattern alone — that's a code-review-time check, not a runtime one. Mitigated per `docs/roadmap.md`'s own acceptance criteria: a route missing `require_role` is an explicit `ai-playbook.md` §11 Code Review Checklist-blocking pattern, enforced by `code-reviewer`, not silently allowed.

## Alternatives considered

- **Resolve `workspace_id` from a session-stored "active workspace" cookie instead of the URL path.** Rejected: contradicts `CLAUDE.md`'s own REST convention requiring `workspace_id` in the URL for every workspace-scoped resource; also weaker, since a cookie-based "active workspace" still needs the identical membership-lookup check before use, so it adds a second state source without removing the need for the check this ADR already specifies.
- **A single combined `get_current_workspace_with_role(minimum: Role)` dependency instead of two composed ones.** Rejected: collapses two distinct concerns (resolving *which* workspace, checking *what role is required*) into one non-reusable dependency; routes that need the `WorkspaceContext` without a specific role floor (e.g. "any member can view") would have no clean way to depend on just the resolution step.
- **Per-route inline role checks (`if member.role not in (...): raise HTTPException(403)`).** Rejected: exactly the pattern this ADR exists to prevent — no shared enforcement point means no guaranteed audit-log coverage and no single place to fix a bug in the role hierarchy.
