# Support-triage dogfooding (Phase 11)

Runbook for standing up AgentVerse's own internal support-ticket triage — an
ordinary workspace running an ordinary agent, using the product exactly as a
customer would (CLAUDE.md §2 AI First: "if our own team struggles to build
something with the product, a customer will too").

There is no seed script and no special-purpose migration for this. The
workspace is created the same way any customer workspace is, and the agent is
installed the same way any customer installs a marketplace template — both
through the existing public API, under normal RBAC. This is deliberate: the
alternative (a bootstrap script that fabricates the workspace with elevated
privileges) would mean the internal team is *not* actually exercising the
same path a customer does, defeating the point of dogfooding.

## Steps

1. **Create the workspace**, authenticated as whichever internal user should
   own it:

   ```
   POST /api/v1/workspaces
   { "name": "AgentVerse Internal" }
   ```

   This is a real workspace with a real owner and real RBAC — not the
   marketplace's `PLATFORM_WORKSPACE_ID` (`marketplace_service/domain/
   templates.py`), which has no members and cannot be logged into. Add any
   other internal teammates who should see support tickets via the normal
   invite flow (`POST /api/v1/workspaces/{workspace_id}/invitations`).

2. **Install the seeded `support-triage` template** into it:

   ```
   POST /api/v1/workspaces/{workspace_id}/marketplace/listings/support-triage/install
   { }
   ```

   `support-triage` has been in the first-party template library since the
   marketplace catalog shipped (`d15a7c94b2e0_seed_agent_templates`
   migration) — published, installable by any workspace, no changes needed
   for this phase. Note the returned `agent_id`; it is what every ticket
   filed against this workspace will pass as `agent_id`.

3. **File a ticket** through the ordinary product surface
   (`/dashboard/{workspaceId}/support`, or `POST .../support-tickets`
   directly) to confirm the whole path end to end: a real agent run is
   triggered, its steps are recorded exactly like any customer agent's, and
   the ticket resolves to a category/priority/draft reply once the run
   completes.

## What this does *not* do

- No tool access. The installed `support-triage` agent carries an empty
  `tools: []` (`marketplace_service/domain/templates.py` — no `tools=`
  argument in its `AgentTemplate` entry), so it can classify, summarize, and
  draft — never send an email, touch billing, or change an account. CLAUDE.md
  §4's "sensitive actions require human approval" holds by construction here,
  not by a runtime policy check that could be bypassed.
- No privilege bypass. Every read/write against this workspace's tickets and
  runs goes through the same `require_viewer`/`require_member` gates and the
  same `agent_runs`/`agent_run_steps` tables as any customer workspace.

## Re-running this

Both steps are idempotent through the existing API: creating a workspace
with the same name a second time produces a second (differently-slugged)
workspace rather than erroring, and installing `support-triage` a second
time into the *same* workspace returns the existing agent (`created: false`)
rather than a duplicate. There is nothing here that requires a fresh
database or a rollback plan.
