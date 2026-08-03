# Completion checklist — enterprise workspace, organizations and security

Against the Definition of Done (CLAUDE.md §19). Every line is either
done, or says plainly what was not done.

## Scope delivered

| # | Requirement | Status |
|---|---|---|
| 1 | Organization architecture (create, rename, delete, transfer, members, suspend) | shipped |
| 2 | Organization profile — logo, brand colour, custom domain, website, support email, description | shipped |
| 3 | Workspace architecture inside organizations (attach/detach, isolation preserved) | shipped |
| 4 | Multi-tenancy — `workspace_id` as sole isolation root | shipped, documented |
| 5 | RBAC — 7 built-in roles | shipped |
| 6 | Custom roles | shipped (additive-only, by design) |
| 7 | Permission inheritance | shipped, computed not hand-maintained |
| 8 | Security Center — security events, trusted devices, login alerts, device history | shipped |
| 9 | Password policy | shipped (see caveat below) |
| 10 | Suspicious-activity detection | shipped (rapid failures, new-device sign-in) |
| 11 | Security score | shipped, explainable |
| 12 | API key expiration | shipped, **enforced** in the bearer path |
| 13 | API key usage metrics | shipped (`use_count`, `last_used_at`) |
| 14 | Audit export CSV/JSON | shipped, injection-safe |
| 15 | Audit activity graph + dashboard | shipped |
| 16 | Organization dashboard | shipped |
| 17 | User presence | shipped as session-derived (see caveat) |
| 18 | SSO (OIDC/SAML, named IdP presets) | pre-existing, unchanged |
| 19 | SCIM provisioning | pre-existing, unchanged |

## Definition of Done

| # | Gate | Status |
|---|---|---|
| 1 | Requirements approved | Spec supplied by the requester; scope audited against shipped code before building rather than rebuilt from scratch |
| 2 | Architecture approved | ADR-0011 records the organization/workspace decision. **No separate `architecture-reviewer` sign-off was obtained** — see gaps |
| 3 | Security reviewed | Threat surfaces addressed and documented in `security-architecture.md`; secret-scanned before commit. **No independent `security-reviewer` pass** — see gaps |
| 4 | Tests passing | 695 api + 289 worker; migrations round-tripped on real Postgres. **No E2E** — see gaps |
| 5 | Documentation updated | 6 documents, same commits as the code |
| 6 | Performance validated | **Not done** — see gaps |
| 7 | Accessibility verified | Built to the standard (semantic markup, labelled controls, `aria-invalid`/`aria-describedby` on errors, status never colour-only, `role="img"` + text alternative on the graph). **No axe-core run or manual screen-reader pass** — see gaps |
| 8 | Monitoring added | Security events and audit logs are themselves observability surfaces; no new service, so no new `/health`/`/ready`. **No dashboard or alert added** — see gaps |
| 9 | Deployment ready | Every migration additive and reversible; rollback is redeploy-previous-tag plus `alembic downgrade`, verified working |
| 10 | Final review complete | This document. **Self-assessed** — no independent `final-qa-reviewer` |

## Documentation delivered

| Document | Covers |
|---|---|
| `docs/adr/0011-organization-workspace-composition.md` | the core architectural decision |
| `docs/architecture/rbac-matrix.md` | roles, permissions, inheritance, custom roles |
| `docs/architecture/multi-tenancy.md` | isolation model, with diagram |
| `docs/architecture/enterprise-schema.md` | schema, ER diagram, migration list |
| `docs/security/security-architecture.md` | trust boundaries, threat handling, known gaps |
| `docs/guides/organizations-and-security.md` | user-facing guide |
| `docs/releases/phase-8-enterprise-testing-report.md` | test coverage, bugs found |

API reference is generated from `apps/api/openapi.json` (92 paths),
regenerated from the running app — never hand-edited.

## Gaps — what was not done

These are real and should not be read past:

1. **No independent review passes.** Architecture, security and final QA
   sign-offs in CLAUDE.md §19 assume a reviewer other than the author.
   This work was self-reviewed. The ADR, threat notes and this checklist
   are inputs *for* those reviews, not substitutes for them.
2. **No E2E tests** for the new pages. Risk here concentrates in
   authorization and SQL, which are covered by 81 real-Postgres
   integration tests, but no automated test has driven these screens in
   a browser.
3. **No accessibility audit.** Built to WCAG 2.2 AA and reasoned about
   throughout, but axe-core was not run and no keyboard or
   screen-reader pass was performed. CLAUDE.md calls accessibility a
   merge gate, so this is an outstanding gate, not a nicety.
4. **No performance measurement.** No latency budget was published or
   measured for the new endpoints. The presence query is a single
   aggregate join rather than N+1 by design, and the export is bounded
   at 10,000 rows — both are design properties, neither is a number.
5. **No screenshots.** The stack was not run against seeded enterprise
   data, so there is no UI evidence attached.
6. **Password policy is not enforced in the sign-up / reset flows.**
   It is enforced at the API boundary and surfaced in the UI. Better
   Auth owns sign-up and reset in `apps/web`, and wiring the org policy
   into those requires resolving a user's organization at sign-up time —
   separate work, deliberately not claimed here.
7. **`max_age_days` is stored but never acts.** No job expires a
   password on schedule. The field records the policy; it does not
   enforce it.
8. **Presence is not live.** `has_active_session` means "holds an
   unexpired session". There is no heartbeat, and the UI says "signed
   in" rather than "online" for that reason.
9. **Device fingerprints are unverified.** They are client-supplied and
   used only for alerting. They are never an authentication factor.

## Rollback

- **Application:** redeploy the previous image tag.
- **Schema:** `alembic downgrade` — verified working for all seven
  migrations, including that the role downgrade *demotes*
  manager/developer/analyst to member rather than promoting them.
- **Blast radius of a rollback:** organization profiles, custom roles,
  security events, trusted devices, password policies and API-key
  expiry configuration are lost. No pre-existing data is affected, and
  every API key reverts to the never-expires behaviour it had before.

## Verdict

**Go with conditions**, self-assessed.

The code is complete, tested and reversible. The conditions are gaps 1,
2 and 3: independent security and architecture review, and the
accessibility gate. Those are process gates this work cannot close for
itself, and CLAUDE.md treats the accessibility one as blocking for UI.
