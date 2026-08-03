# Testing report — enterprise workspace, organizations and security

Covers the work delivered as "Phase 8": seven-tier RBAC with custom
roles, organization profile, Security Center, API-key expiry, audit
export and activity, and the organization dashboard.

Note on naming: this initiative is *not* the numbered Phase 8 in
`docs/roadmap.md` (Prompt Versioning / Marketplace Templates). It is
net-new enterprise scope layered on top of the existing platform, which
is why no migration or module is named `phase_8_*`.

## Gate results

| Gate | Command | Result |
|---|---|---|
| Python lint | `uv run ruff check .` | pass (api, worker) |
| Python format | `uv run ruff format --check .` | pass (api, worker) |
| Types (Python) | `uv run mypy src` | pass — 177 files (api), 60 (worker) |
| Tests (api) | `uv run pytest -q` | **695 passed** |
| Tests (worker) | `uv run pytest -q` | **289 passed** |
| Migrations | `alembic upgrade head` → `downgrade` → `upgrade` | pass, real Postgres |
| Types (web) | `npx tsc --noEmit` | pass |
| Lint (web) | `npx eslint app lib components --max-warnings=0` | pass |
| Build (web) | `npm run build` | pass |
| Contracts | regenerated from OpenAPI | pass |

81 of the 695 API tests are integration tests running against real
Postgres. They are not mocked: a fake would let the exact class of bug
these cover pass silently.

## What each new test actually protects

Tests are listed by the failure they would catch, not by the function
they call.

### `tests/auth_service/domain/test_permission_matrix.py` (27)

- Adding the three new tiers did **not** change what `require_role(ADMIN)`
  admits. Asserted structurally against `LEGACY_ROLES`, not spot-checked.
- Every tier is a proven **superset** of every tier below it, so
  inheritance cannot silently develop a hole.
- The rank order and the permission matrix agree.

### `tests/auth_service/integration/test_custom_roles.py` (4)

- A custom role adds grants without changing its holder's role floor.
- The `custom_role_id` join resolves; the `NULL` fast path is unaffected.

### `tests/auth_service/domain/test_security.py` (15)

- Every `SecurityEventType` has a severity — a new event type cannot
  ship without one and sort unpredictably.
- `password_violations` returns **all** violations, not the first.
- Two-factor scoring is proportional, so a partial rollout scores
  between none and full rather than zero.
- An **empty workspace is not penalised** for two-factor coverage
  (0 members means 0 uncovered, not 0%).
- The score **equals the sum of its factors** — a number the breakdown
  cannot explain is unactionable.
- Grade boundaries checked against the real weights. (This test initially
  asserted the wrong grade; the weights were correct and the test was
  fixed, not the code.)

### `tests/auth_service/integration/test_security_center.py` (12)

- **Severity is derived, not caller-supplied** — verified through the
  real column.
- An event with **no user** is recordable (failed login for an unknown
  address must not be dropped — that is the enumeration signal).
- The `event_type` CHECK rejects an unknown value, proving the database
  backstop rather than assuming it from the migration file.
- Re-trusting a device updates rather than duplicating; re-trusting a
  **revoked** device un-revokes it.
- **Revoking another user's device reads as not-found** (Rule 11) and
  leaves the real device active.
- The `password_policies` CHECK rejects a policy below the platform
  floor.
- **An expired API key does not authenticate** — the whole point of
  storing an expiry, and only provable against the real SQL.
- `use_count` increments per authentication; `count_non_expiring`
  counts only active, never-expiring keys.

### `tests/auth_service/application/test_audit_export.py` (10)

- CSV header order is **fixed and declared**, so a dataclass field
  reordering cannot reshape an export someone's script parses.
- **Formula injection is neutralised** for `=`, `+`, `-`, `@` — an
  exported audit log opened in a spreadsheet is otherwise a real
  code-execution path.
- An ordinary value is *not* mangled by that guard.
- JSON keeps real types (metadata stays an object, nulls stay null)
  rather than flattening the way CSV must.
- An empty export still produces a valid document (header-only CSV,
  `[]`), not a zero-byte file that reads as a failure.

### `tests/auth_service/integration/test_organization_dashboard.py` (5)

- Presence reports the **most recent** session, not an arbitrary one.
- A member with only **expired** sessions is not reported active, but
  still reports when they were last seen.
- A member who has **never signed in still appears** — the outer join is
  real, so nobody vanishes from the dashboard.
- Stats count workspaces, members and roles correctly.
- A **suspended member is counted separately, not dropped** — they still
  occupy a seat and still need to be visible.

### `tests/auth_service/integration/test_organization_settings_repository.py` (3)

- The `ON CONFLICT` upsert updates in place.
- Deleting an organization **cascades** to its settings — proven against
  the real FK.

## Bugs found and fixed during this work

Reported because they are the useful part of a test report.

1. **ADR number collision.** The organization/workspace composition ADR
   was numbered 0006, which already belonged to the provider-abstraction
   ADR. Renumbered to 0011 with all 21 citations updated.
2. **`Mapped[Role]` was a lie.** Moving role columns off the Postgres
   enum to TEXT made SQLAlchemy return bare strings; `role is Role.OWNER`
   silently failed while `==` kept working. Caught by 12 tests, fixed
   with one `RoleType` decorator rather than patching each converter.
3. **`ruff format --check` was already failing on `main`** — a required
   CI gate, red on 46 files never touched by this work. Verified against
   the committed versions at HEAD, then fixed in a separate
   formatting-only commit so the reformat is reviewable as a no-op.
4. **Exhaustive `Record<Role, …>` maps broke on contract regeneration.**
   Three frontend maps did not cover the new roles. This is the failure
   mode TypeScript's strict settings exist to produce; fixed rather than
   widened.
5. **The audit export could not have worked as first designed.** It
   pointed a download link at `apps/api`, which is internal-only and
   bearer-authenticated server-side — the browser has neither a token
   nor a route. Replaced with a `apps/web` route handler that
   authenticates and streams.
6. **`bg-brand` is not a token.** The activity graph used it; only the
   numbered ramp exists, so the bars would have rendered with no
   background. Changed to `bg-brand-500`.
7. **Fake repositories diverged from real ones.** The API-key fake did
   not filter expired keys, which would have let unit tests pass while
   the real authentication path refused the key. The fakes now mirror
   the real filters.

## What is not covered

Stated plainly rather than left to be discovered:

- **No E2E (Playwright) tests were added** for these surfaces. The
  browser-only behaviour here (a form, a table, a download link) is
  thin, and the risk concentrates in the authorization and SQL layers,
  which are covered above. This is a deliberate placement, not an
  omission — but it does mean the new pages have not been exercised in
  a real browser by an automated test.
- **No screenshots.** The dev stack was not run against seeded
  enterprise data as part of this work, so no UI evidence is attached.
- **`max_age_days` has no enforcement job**, so there is no test for
  password expiry actually expiring anything. The field is configuration
  only, and the security architecture doc says so.
- **Password policy is not wired into Better Auth's sign-up and
  password-reset flows.** Enforcement exists at the API boundary; the
  `apps/web` auth flows would need to resolve the user's organization at
  sign-up time, which is separate work.
- **Load/performance testing** was not run against the new endpoints.
  The dashboard presence query is a single aggregate join by design
  rather than N+1, but that is a design property, not a measured one.
