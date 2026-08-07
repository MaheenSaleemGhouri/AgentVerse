---
title: Install a template
summary: Copy a first-party template or a community listing into your workspace as an editable agent.
pillar: marketplace
last_verified: "2026-08-07"
status: published
order: 1
---

The marketplace is the fastest way to a working agent. Installing copies a listing's configuration into your workspace as a new agent that is yours to edit — you are not subscribing to someone else's agent, you are taking a copy.

## Prerequisites

- `member` or higher.

## The first-party template library

Twelve templates ship with the platform, marked **official**:

| Slug | What it does |
| --- | --- |
| `research-assistant` | Answers questions from sources, with citations. |
| `code-reviewer` | Reviews a diff for correctness and clarity. |
| `sql-analyst` | Turns a question about a schema into SQL. |
| `support-triage` | Classifies and routes inbound support messages. |
| `meeting-notes` | Turns a transcript into decisions and actions. |
| `content-writer` | Drafts long-form content from a brief. |
| `sales-qualifier` | Scores an inbound lead against your criteria. |
| `onboarding-guide` | Walks a new user through a process. |
| `document-summarizer` | Summarises a long document faithfully. |
| `data-cleaner` | Normalises messy tabular input. |
| `email-drafter` | Drafts a reply in your voice. |
| `process-automator` | Turns a described process into repeatable steps. |

```bash
agentverse templates
agentverse install research-assistant --name "Our researcher"
```

## Install from the API or an SDK

```python
from agentverse import AgentVerse

with AgentVerse() as client:
    result = client.marketplace.install("research-assistant", name="Our researcher")
    print(result["agent_id"], result["created"])
```

`created` is the field to check. Installing is idempotent per workspace, listing and version: a repeated install returns the agent you already have rather than a second copy. `created: false` means "you already had this", which is different from "it worked" and worth distinguishing in any script that wraps it.

Pin a version with `version_number` if you want a specific one; the default is the latest published version.

## What comes across, and what does not

Installed: the system instructions, the model, and the tool configuration.

**Not installed: knowledge bases.** The listing named the publisher's knowledge bases, and there is nothing in your workspace to remap them to. An agent built around retrieval will install cleanly and then answer without any — attach one of your own. See [Ground an agent in your documents](/docs/agent-builder/knowledge-bases).

**Not installed: credentials.** MCP credentials belong to the workspace that stored them and never travel with a listing. Connect your own under **Integrations**.

## After installing

The installed agent is a normal agent in your workspace. Edit it, publish a new version, run it. Changes you make are yours and do not propagate back; a later version of the listing does not overwrite your copy.

## Expected result

A new agent in **Agents**, editable, with the listing's instructions and model.

## Troubleshooting

**Installing again returned the same agent.** Working as intended — see `created` above.

**The agent runs but ignores documents.** No knowledge base came across. Attach one.

**A tool does not work.** It needs an MCP integration you have not connected.

## Related guides

- [Publish a listing](/docs/marketplace/publish-a-listing)
- [Ground an agent in your documents](/docs/agent-builder/knowledge-bases)
