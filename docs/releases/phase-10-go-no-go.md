# Phase 10 — AI Ecosystem, Marketplace & Developer Platform

**Go / no-go record.** Aggregates the milestone sign-offs, states what
shipped, and — more usefully — states what did *not*, so the gaps are a
decision on the record rather than something discovered later.

| | |
|---|---|
| Milestones | 8 (`v0.11.0-alpha.m1` … `m8`) |
| Commits | 8 |
| ADRs | 0013 (cross-context search), 0014 (in-product assistant) |
| Verdict | **Go, with conditions** — the conditions are listed at the bottom and none of them block merge |

---

## What shipped

### The marketplace (M1, M2, M3, M7)

A fifth bounded context in `apps/api`, layered like its siblings, plus
the customer-facing catalog, listing pages, install flow, reviews, and
publisher console.

**The catalog is the platform's one deliberate tenancy exception.**
Browsing published listings is the only read in the system that does not
filter by `workspace_id` — a marketplace nobody outside your workspace
can see is not a marketplace. Everything around it stays scoped: drafts
and rejections are publisher-only, every write is publisher-only, and a
hidden listing answers 404 rather than 403 so its existence is not
leaked by the difference.

**An install is a copy, not a subscription.** Installing freezes a
listing's version into a new agent in the installing workspace. The
publisher cannot later change what someone already installed, and
unlisting does not break anyone who installed before it.

**Moderation is platform authority, not a workspace role.** Approving a
listing is a judgement about a *different* workspace's listing, which no
workspace role can express — routing it through `require_role` would
have let publishers approve themselves. It goes through
`platform_admins` and `require_platform_admin`, which answers 404 on
denial and audit-logs both grants and denials.

Twelve first-party templates seed the catalog, so a new workspace has
something to install on day one rather than an empty grid.

### Rate limiting and webhooks (M4)

Per-workspace, per-plan sliding-window rate limiting enforced at the
gateway before expensive work begins, failing closed when Redis is
unavailable. Outbound webhooks with HMAC-signed deliveries, bounded
retry, a dead-letter path, and SSRF egress control on every outbound
call.

### The developer platform (M5, M7)

Python and TypeScript SDKs and a CLI, all generated against the same
OpenAPI contract the frontend types come from — one source, three
consumers, no hand-written client. Plus an in-product API explorer.

**The explorer is GET-only by construction, not by a filter.** An
explorer that could fire `POST /runs` would spend a customer's money
from a page whose whole point is clicking things to see what happens.
And the client sends an endpoint *id*, never a path: the path is rebuilt
server-side from a fixed catalog, so the action cannot be turned into an
open proxy carrying the caller's bearer token.

### Documentation portal and global search (M6)

Eleven guides organised by product pillar, rendered at build time and
statically generated. Each was reproduced against the running product
before its `last_verified` date was set. A twelfth
(`platform/the-assistant`) was added alongside M8 — see condition 9.

Global search spans agents, knowledge bases, teams, and listings from
⌘K. It is a sixth bounded context owning only fan-out and ranking — each
searchable context grows a `search_*` method on its *own* repository, so
search can never disagree with the owning context about what a live
agent is (ADR-0013).

**Postgres GIN expression indexes, not generated `tsvector` columns.** A
generated column rewrites the whole table under `ACCESS EXCLUSIVE`; an
expression index needs no schema change at all. The failure mode this
introduces — the query's expression drifting from the index's — produces
no error and no log line, so an integration test asserts each query
picks a Bitmap Index Scan under `enable_seqscan = off`. That test is the
only thing standing between a working index and a silent sequential scan
forever.

### The assistant and the moderation panel (M8)

An in-product assistant, reachable from every dashboard page, that
answers questions from the shipped documentation and cites what it used.

**It is not an agent run.** One bounded provider call, no tool loop,
nothing it can act on. Help questions therefore stay out of run history
and quota, and there is no loop to bound or side effect needing a policy
check. ADR-0014 records what would have to change if it ever gains the
ability to act — a new design, not a parameter.

**Grounding comes from a generated index.** The markdown under
`apps/web/content/docs/` stays the single source of truth; a script
turns it into heading-bounded passages, and a test fails when the
committed index has drifted, naming the command to run. Same
arrangement `packages/contracts` uses for the OpenAPI types, and for the
same reason: a runtime cannot read another app's source tree, but two
hand-maintained copies are not an option either.

**Untrusted content is isolated in both directions.** Passages are
rendered into delimited blocks framed as reference material, never
instructions — the guides are first-party today, but that defence has to
predate the first user-authored page. Coming back out, the answer is
parsed into data and rendered as React elements; there is no
`dangerouslySetInnerHTML` in the path, and only `/docs/...` hrefs
survive as links, so a model-invented URL renders as the literal text it
is.

---

## Two gates added this phase

Both exist because a class of failure was reaching production checks
that neither `tsc` nor eslint could see.

**`server-only-boundary.test.ts`** fails when a Client Component imports
a *value* from a `server-only` module. That mistake is invisible to the
type checker and the linter; the bundler catches it around ninety
minutes into a production build, with an error naming a file three
imports away from the cause. It cost two builds before the gate existed.
The gate runs in two seconds, and was verified to fail against a planted
violation before being trusted.

**`api-explorer/contract.test.ts`** validates every explorer path
against `apps/api/openapi.json`. It caught two paths written from
memory on its first run.

---

## What did not ship

**1. Paid listings still do not charge.** `price_cents` is recorded,
displayed, and formatted correctly everywhere, and the install dialog
tells the user explicitly that they will not be charged. Nothing
collects the money. Open since M2 and stated at every milestone since —
this is a deliberate scope line, not an oversight, but a listing priced
at $19 that installs for free is a commercial gap, not a technical one.

**2. The Workflow Marketplace is inert.** It exists as a second listing
kind that raises `WorkflowListingsNotYetSupportedError`. There are no
workflows to market until the DAG builder ships; building a storefront
for them first would have been scaffolding. Recorded as a correction to
the phase brief before M1 started.

**3. Runs are not searchable.** Global search covers agents, knowledge
bases, teams, and listings. Runs are absent because there is still no
read path over `agent_runs` — the Phase 4 gap `feature-availability.ts`
tracks as `runHistory`. Searching runs is blocked on that endpoint, not
on this phase.

**4. Satoshi was not added.** The brief specified Satoshi, Geist and
JetBrains Mono. JetBrains Mono shipped in M6, scoped to documentation
code blocks. Satoshi was refused and the refusal stated before M1:
swapping the body font restyles every existing page, which the same
brief forbids. Geist remains the body font.

**5. The mascot is a CC0 placeholder.** The 3D scene on the auth page
and the 2D mark on the assistant launcher are both placeholder
characters, not branded assets. Stated at phase start.

**6. The SDKs are not published.** Both build, both are tested, neither
is on PyPI or npm. Publishing is outward-facing and effectively
irreversible at a version number, and no credentials exist in this
environment. It is a release step with a human on it, not a code gap.

**7. Assistant turns are not metered.** Token usage is logged per turn
with `workspace_id` and `session_id`, but nothing aggregates it into
`billing_usage_events`. Cost is bounded by `MAX_ANSWER_TOKENS`, the
per-workspace rate limit, and the question-length cap. If assistant cost
ever needs billing, that is a metering change against data already being
recorded — not a re-architecture.

**8. Query plans are verified at development scale.** The four search
indexes are proven to be *used* — that is what the `EXPLAIN` test
asserts. Their behaviour at production row counts is not something this
environment's data volume can demonstrate.

**9. The assistant has not been exercised against a live provider or in
a browser.** Its logic is covered end to end against fakes — retrieval,
prompt assembly, persistence on success, non-persistence on failure,
isolation against both a foreign tenant and a same-workspace colleague —
and the repository tests run against real Postgres. But no answer has
been generated by a real model, and the panel has not been driven with a
keyboard or a screen reader in a running browser. The
`platform/the-assistant` guide is therefore written from the shipped
implementation rather than reproduced against it, which is a weaker
claim than the other eleven guides carry. Before the assistant is
announced: one real streamed answer in staging, and one manual
keyboard + screen-reader pass over the panel.

---

## Verification

| Suite | Result |
|---|---|
| `apps/api` — unit + integration | 1458 passed (real Postgres via pgvector container) |
| `apps/web` — vitest | 166 passed across 14 files |
| `apps/web` — `tsc --noEmit` | clean |
| `apps/web` — eslint | clean |
| `apps/api` — `mypy --strict src` | clean, 346 source files |
| `apps/api` — ruff format + check | clean |
| `apps/web` — `next build` | exit 0; shared JS 103 kB, unchanged by M8 |
| Migrations | `a1c7e35d9f84` and `b6e2f04a9d17` each executed upgrade → downgrade → upgrade against real Postgres |

One environment note worth recording, because it cost real time: on this
WSL host, `next build` against `/mnt/c` stalls indefinitely in the 9P
filesystem layer. The same build off the Linux filesystem completes in
about 2.5 minutes. Builds for this phase were verified from a synced
copy at `~/av-build`.

---

## Sign-off

| Gate | Owner | Status |
|---|---|---|
| Architecture | `architecture-reviewer` | ADR-0013 (search context, expression indexes, tsquery safety, non-standard envelope) and ADR-0014 (assistant as a bounded call, generated docs index, unit-of-work scoping) |
| Database | `database-architect` / `postgresql-expert` | Both migrations additive and reversible, downgrades executed; GIN indexes built `CONCURRENTLY`; index *use* asserted, not assumed |
| Security | `security-reviewer` | `to_tsquery` fed from an alphanumeric allowlist, never escaping; assistant passages structurally delimited; answer links allowlisted to `/docs`; moderation 404s on denial and audit-logs both outcomes; explorer cannot proxy an arbitrary path |
| Tenant isolation | `authorization-expert` | Catalog exception documented and bounded; assistant sessions scoped by workspace *and* user in the `WHERE` clause, asserted against real Postgres for both a foreign tenant and a same-workspace colleague |
| Frontend | `senior-frontend-engineer` | Server-only boundary now a permanent gate; assistant panel lazy so shared JS is unchanged; streamed deltas buffered and flushed on an interval, never `setState` per token |
| Accessibility | `accessibility-expert` | Streaming answer in an `aria-live="polite"` region; Radix focus trap and Esc retained on every dialog and sheet; rating input a `radiogroup`; status never colour-alone; `prefers-reduced-motion` honoured on the launcher. **Conditional on the manual pass in condition 9** — the assistant panel has been reviewed in code, not driven with a screen reader |
| Testing | `testing-architect` | +71 backend tests this milestone, +25 frontend; isolation and ordering asserted against real Postgres rather than fakes; no exact-match assertions on model output |
| Documentation | `documentation-engineer` / `technical-writer` | Twelve user-facing guides, eleven reproduced against the running product; two ADRs; drift gate ties the assistant's corpus to the guides |

**Verdict: go, with the nine conditions above recorded.**

Conditions 1 and 6 are the ones that matter commercially — paid listings
collect nothing, and the SDKs are not on a registry. Condition 9 is the
one that gates announcing the assistant. All three need a human
decision or a live environment rather than more code.
