# OWASP Top 10 audit — Phase 6 surfaces

`CLAUDE.md` §10 and §19 item 3. The standing audit `owasp-expert` owns,
distinct from the per-PR `security-reviewer` gate in
`phase-6-security-review.md`. Every applicable category gets an explicit
"reviewed, no finding" or a filed finding with severity, reproduction,
and an owner — a category left unmentioned is not the same as one that
passed.

Mapped to AgentVerse's real surfaces, not generic checklist prose. Scope
is the same as the security review: the integrations API, the tool
boundary, the MCP client, the credential envelope, and the migration.

## A01 — Broken access control

**Reviewed. No finding.**

The cross-workspace case is the one that matters here, and it holds at
three independent layers rather than one:

- **Routing.** No Phase 6 handler reads `workspace_id` from a path,
  body, or query parameter; every one resolves it from
  `context.workspace_id`, which comes from the authenticated identity.
  Verified by reading every route in `integrations/router.py`.
- **Query.** Every repository method filters on `workspace_id`.
- **Cryptography.** Credential AAD binds ciphertext to
  `(workspace_id, installed_server_id, key)`, so a row moved between
  workspaces at the database level does not decrypt. Access control
  that survives a database-level mistake is a materially different
  guarantee from access control enforced only in application code.

Cross-workspace reads return `404`, not `403`, so an install's
existence is not disclosed. Covered by cross-workspace tests.

The tool-permission layer is separate and also deny-by-default: a
`read_only` grant refuses a mutating tool **before execution**, and
independently of the model's judgment, so an injected instruction
arguing for the call changes nothing.

## A02 — Cryptographic failures

**Reviewed. No finding.**

AES-256-GCM envelope encryption, per-row DEK wrapped by a KEK from the
environment. No custom crypto. `cryptography` is pinned `>=48.0.1` after
this audit's dependency scan found GHSA-537c-gmf6-5ccf in the version in
use — see the security review; that finding was fixed, not noted.

`CredentialCryptoError` deliberately carries no detail about *why*
decryption failed, which denies an attacker an oracle. No credential
value appears in any response schema; the detail endpoint returns key
name, last-four, and timestamps only, including to an owner.

## A03 — Injection

**Reviewed. No finding**, across three injection classes that this
surface exposes and a generic checklist would merge:

- **SQL.** No raw string-built SQL in application code. The only
  f-string SQL in the Phase 6 diff is in the Alembic migration,
  interpolating hardcoded enum member names defined in the same file;
  no runtime value reaches it.
- **Prompt injection.** Tool results are the primary vector — a
  compromised or hostile MCP server returns text that re-enters the
  model's context. `sanitize_result` is the only path back in, and it
  never returns bare text: output is capped and wrapped as untrusted
  content with explicit provenance. A caller cannot accidentally
  concatenate an unwrapped result into instructions because there is no
  unwrapped result to concatenate. Tested against a forged closing tag.
- **Argument injection.** Tool arguments are model output, therefore
  untrusted input, and are validated against the declared JSON schema
  before execution. Catalog stdio arguments are tested for shell
  metacharacters.

## A04 — Insecure design

**Reviewed. No finding**, with one design limitation recorded.

The threat model (`threat-model-tool-execution.md`) was authored before
implementation and its controls are present: bounded loops on all three
axes (step, cost, time), a circuit breaker, per-run call budgets, and
refusals ordered cheapest-first so a denied call cannot become an
amplifier — now measured at 0.60× the cost of a permitted call.

**Limitation:** a *stuck-open* circuit breaker is not detectable from
metrics, a consequence of dropping unbounded labels. Recorded in the
monitoring runbook. It degrades availability, not security.

## A05 — Security misconfiguration

**Reviewed. One finding, fixed.**

`AGENTVERSE_CREDENTIAL_KEK_V1` had been written into
`apps/worker/.env.example`. Two problems: it put a key-shaped value into
version control, and it was un-prefixed in a file parsed by a settings
model with `extra="forbid"`, so it broke startup. Fixed in `9eb7ffb` —
the key is documented as a process-level variable with the reason it is
shared between services, and there is no default anywhere, so a missing
key fails startup loudly.

Confirmed absent: no secret in source, no `os.environ.get(k, default)`
fallback, no secret in a `NEXT_PUBLIC_*` variable, none in an image
layer. The Alertmanager config added in this phase reads receiver
credentials from mounted files rather than inline values.

The worker's `/internal/metrics` endpoint is new attack surface and was
reviewed as such: the service is not internet-routable, and the payload
carries no tenant identifier by construction — no metric has a
`workspace_id` label. Asserted by a test rather than by inspection.

## A06 — Vulnerable and outdated components

**Reviewed. One finding fixed, two accepted.**

`pip-audit` and `pnpm audit` run in CI on every PR and nightly. At audit
time: `cryptography` 46.0.7 (**fixed**, it seals every credential);
`starlette` 0.46.2, 8 advisories, transitive through the
`fastapi>=0.115,<0.116` pin in both services (**accepted** — the fix is
a FastAPI major bump, which is a cross-service upgrade with its own
contract surface, owner `security-engineer`); `pytest` and
`brace-expansion` (**accepted**, dev-only, in no shipped image).

## A07 — Identification and authentication failures

**Not applicable to this phase.** Phase 6 adds no authentication
surface; identity is verified upstream by the Phase 1 gateway
dependency and consumed here. Recorded explicitly so its absence is a
scope statement rather than an omission.

The one adjacent item: **OAuth2 is scaffolded, not finished.** PKCE
storage and single-use consumption exist and are tested; the
authorize-redirect and token-exchange endpoints do not. Nothing
half-authenticated is reachable — those catalog entries install but
cannot complete a flow. This is an incompleteness, not a vulnerability,
and it is a release-note obligation: claiming those integrations work
would be a false claim.

## A08 — Software and data integrity failures

**Reviewed. No finding.**

Agent and integration configuration is `jsonb` validated by Pydantic at
the API boundary; no pickle, no `eval`, no dynamic import of
user-supplied names anywhere in the diff. MCP tool schemas arriving from
a third-party server are normalised before use rather than trusted.

A server that changes its advertised tool surface between runs is
detected (`diff_tool_surface`) rather than silently accepted — the
integrity property that matters when the tool list is supplied by
someone else.

## A09 — Security logging and monitoring failures

**Reviewed. Previously a finding; now closed except for notification.**

Every path through the boundary writes a `tool_calls` row **including
every refusal**. A blocked SSRF attempt that left no trace would make
the egress control unauditable, which is most of its value.

At the time of the security review nothing was instrumented; that is now
closed. `agentverse_egress_denied_total{range}` and
`agentverse_credential_unseal_failures_total` are emitted, scraped, and
covered by alert-rule unit tests, and their series exist from process
start so `increase(...) > 0` can distinguish "no denials" from "not
reporting".

**Residual: no receiver is provisioned**, so nothing pages a human yet.
For an audit category that is specifically about failing to notice, that
is the honest remaining state — detection exists, notification does not.

Privacy holds: general logs carry tool name, status, duration, and
denial reason; argument and result content is confined to `tool_calls`,
size-capped, behind the workspace-scoped API.

## A10 — Server-side request forgery

**Reviewed. No finding.** The most thoroughly covered category here, as
it should be — an agent that fetches URLs is an SSRF engine by design.

Three properties beyond an IP blocklist:

- **Every resolved address is validated**, not just the first. A
  hostname with several A records where one is public is otherwise a
  trivial bypass.
- **The validated address is pinned.** The caller dials the approved IP
  and sends the original `Host` header rather than handing the hostname
  back to an HTTP client that would resolve it again. That second
  resolution is DNS rebinding, and a validate-then-fetch guard does not
  stop it.
- **Redirects are re-validated per hop.** A `302` to
  `169.254.169.254` is the same attack with an extra step.

Denied by default: RFC1918, loopback, link-local including cloud
metadata (v4 and v6, including IPv4-mapped and 6to4 forms), CGNAT,
multicast, reserved, plus a `is_global` backstop so a future special-use
range is caught without a code change. Scheme is an allowlist, so
`file:`/`gopher:`/`dict:` are denied rather than forgotten.

32 adversarial tests. Infrastructure-level egress policy is intended as
the second layer; **it is not yet deployed**, so this guard is currently
the only one — noted because the threat model claims defence in depth
and that claim is not yet true in any environment.

## Findings summary

| Category | Verdict |
| --- | --- |
| A01 Broken access control | Reviewed, no finding |
| A02 Cryptographic failures | Reviewed, no finding |
| A03 Injection | Reviewed, no finding |
| A04 Insecure design | Reviewed, no finding (one availability limitation) |
| A05 Security misconfiguration | **1 finding, fixed** (`9eb7ffb`) |
| A06 Vulnerable components | **1 fixed, 2 accepted with owner** |
| A07 Auth failures | Not applicable (scope statement) |
| A08 Integrity failures | Reviewed, no finding |
| A09 Logging & monitoring | Was a finding; **closed except notification** |
| A10 SSRF | Reviewed, no finding (second layer not deployed) |

## What this audit is not

It is a **code and design review against the Top 10**, performed by
reading the implementation and running the dependency scanners. It is
not a penetration test: the egress guard and the credential envelope
have been reasoned about and unit-tested, never attacked by someone
trying to break them. No fuzzing, no hostile MCP server stood up against
a live worker.

For a surface whose whole purpose is executing third-party code paths on
a tenant's behalf, that gap is worth naming rather than letting a green
table imply more assurance than was actually obtained.
