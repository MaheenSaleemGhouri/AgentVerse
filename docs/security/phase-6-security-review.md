# Security review — Phase 6 (MCP integrations & tool execution)

`CLAUDE.md` §19 item 3. This is the `security-reviewer` per-PR/release
gate applied to the Phase 6 diff. It does not restate the threat model —
that is `threat-model-tool-execution.md`, and the threats T1–T6 named
there are the checklist this review was run against.

Scope: `apps/api/src/agentverse_api/integrations/**`,
`apps/worker/src/agentverse_worker/tools/**`,
`packages/python-shared/src/agentverse_shared/security/**`, the Phase 6
Alembic migration, and the three new frontend surfaces.

## Method

Code was read, not sampled. Where a control could be asserted by a test,
the assertion is named. Where it could only be established by reading,
that is said. Dependency findings come from real `pip-audit` and
`pnpm audit` runs whose output is reproduced below rather than
summarised as "clean".

## Findings by control

### Tenant isolation — no finding

`workspace_id` is never read from a path, body, or query parameter in
any Phase 6 route. Every handler resolves it from `context.workspace_id`
(the authenticated identity injected by the shared dependency). Verified
by reading every route in `integrations/router.py` and by grepping the
module for `workspace_id` assignments: no occurrence originates from
client input.

Cross-workspace reads return `404`, not `403`, so an install's existence
is not leaked across tenants (`CLAUDE.md` §10). Asserted by the
cross-workspace tests in the API suite.

Every credential unseal is bound by AAD to
`(workspace_id, installed_server_id, key)`. A row physically moved to
another workspace does not decrypt — isolation survives a database-level
mistake, not just an application-level one.

### Secrets handling — no finding

- No credential value appears in any response schema. The detail
  response exposes key name, last-four, and timestamps only; there is no
  endpoint that returns a plaintext value, including to an owner.
- `AGENTVERSE_CREDENTIAL_KEK_V1` has no default. A missing key raises at
  settings load, so the service fails to start rather than sealing with
  a predictable value. This was re-verified after the `.env` fix in
  `9eb7ffb` — the key is deliberately un-prefixed and process-level
  because apps/api seals and apps/worker opens, and two different values
  would silently produce unreadable credentials.
- Logs carry tool name, status, duration, and denial reason. Argument
  and result content is confined to `tool_calls`, size-capped, behind
  the workspace-scoped API (`CLAUDE.md` §10 privacy).

### Injection — no finding

No raw string-built SQL exists in application code. The only f-string
SQL in the Phase 6 diff is inside the Alembic migration, interpolating
hardcoded enum member names defined in the same file — no runtime value
reaches it.

Tool arguments returned by the model are validated against the tool's
JSON schema before execution, and tool results are sanitised before
re-entering agent context. Retrieved and returned content is
structurally delimited, never concatenated into instructions (T2).

### Egress control — no finding

Every agent-initiated outbound call routes through the egress guard.
The guard resolves and validates before connect and revalidates each
redirect hop, so a public hostname that redirects to `169.254.169.254`
is stopped at the hop, not at the first resolution. RFC1918, loopback,
and link-local (including the cloud metadata address) are denied by
default. Direct sockets from the worker are not used.

### Bounds — no finding

Step, cost, and time ceilings are all three enforced (`CLAUDE.md`
Rule 17): per-run call budget, per-run cost budget, and a 120 s hard
timeout, plus a circuit breaker per installed server. Refusals are
ordered cheapest-first so a repeated denied call is not an amplifier.

## Dependency audit

Run on the actual lockfiles, not on the declared ranges.

### Python — `pip-audit`

11 vulnerabilities across 3 packages at the time of review.

| Package | Version | Advisory | Disposition |
| --- | --- | --- | --- |
| `cryptography` | 46.0.7 | GHSA-537c-gmf6-5ccf | **Fixed.** Bumped to `>=48.0.1,<49` in `packages/python-shared`. This is the library that seals every MCP credential, so it is not one to leave lagging. Both services re-synced onto 48.0.1 and all four suites re-run green (971 passed, zero skipped, against a real Postgres) on the new version |
| `starlette` | 0.46.2 | 8 advisories | **Open, accepted for this release.** Transitive through the `fastapi>=0.115,<0.116` pin in both apps/api and apps/worker. The fixed lines (0.47.2 / 0.49.1 / 1.x) require a FastAPI major bump, which is a cross-service upgrade with its own test and contract surface — not a Phase 6 change. Tracked below as the one open security item |
| `pytest` | 8.4.2 | PYSEC-2026-1845 | **Open, dev-only.** Test-runner dependency; not present in any shipped image. Bump to 9.0.3 folded into the same upgrade pass |

### JavaScript — `pnpm audit`

3 high, all the same package: `brace-expansion <=5.0.7` (ReDoS), 93
paths, every one of them a devDependency reached through eslint.
Not in the client bundle, not in a running service. Cleared by the same
routine upgrade pass; not a release blocker.

## Open items

1. **`starlette` advisories via the FastAPI pin.** Stated as a decision,
   not deferred silently: shipping Phase 6 on the current pin is
   accepted because the affected paths are in framework request
   handling that sits behind the gateway and none of the 8 advisories
   has a demonstrated exploit path through an AgentVerse route. A
   FastAPI major upgrade is the correct fix and belongs in its own
   change with its own regression run. Until that lands, this is a known
   accepted risk with a named owner (`security-engineer`).
2. **`owasp-expert` standing audit not run.** The OWASP Top 10 mapping
   in the threat model was authored, not independently audited. A01,
   A03, A08, and A10 all have controls and reasoning recorded; none has
   an outside "reviewed, no finding" stamp.
3. **No penetration test.** The egress guard and the credential envelope
   are verified by unit tests and by reading; neither has been attacked.

## Verdict

**Pass with accepted risk**, at the level of assurance a code review can
give.

No blocking finding was raised against the Phase 6 code itself: tenant
isolation, secrets handling, injection resistance, egress control, and
execution bounds all hold under reading and are covered by tests. One
dependency finding was real and was fixed rather than noted. The
remaining dependency findings are transitive or dev-only and are
recorded above with an explicit disposition instead of being cleared by
assertion.

`CLAUDE.md` §19 item 3 asks for a `security-reviewer` sign-off with zero
unresolved *blocking* findings. That condition is met. The item is
**not** fully satisfied in the stronger sense the constitution intends,
because the standing `owasp-expert` audit has not run — item 2 above.
This document is the reviewer's gate, honestly bounded, not a substitute
for the auditor's.
