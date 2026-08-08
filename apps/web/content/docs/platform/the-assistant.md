---
title: The AgentVerse assistant
summary: Ask questions about the product from any dashboard page, and check the answers against the guides they came from.
pillar: platform
last_verified: "2026-08-08"
status: published
order: 4
---

The assistant is the small robot button in the bottom-right corner of every dashboard page. It answers questions about how AgentVerse works — where a setting lives, what a role can do, why a run failed — using these guides as its source.

## Asking a question

Select the button, or ask one of the suggested questions to start. Enter sends; Shift+Enter starts a new line.

Answers stream in as they are written, and finish with links to the guides they came from. Follow a link before acting on anything that changes billing, permissions, or production agents — the link is there so you can check.

## What it can and cannot do

The assistant reads documentation. It does not act on your workspace.

It cannot create an agent, start or cancel a run, change a setting, issue a key, or edit billing. If an answer tells you to do one of those, it is telling you where *you* do it. There is no way to ask it to do the thing for you, and that is deliberate: an assistant with a hand on production is a different product with a different risk profile.

It also does not read your workspace. It cannot see your agents, your runs, your documents, or your usage — so it cannot answer "why did *my* run fail last night". For that, open the run and read its trace ([Watch a run](/docs/observability/watch-a-run)).

## When it says it could not find something

The assistant is instructed to say so plainly rather than guess. An answer of "that is not covered in the guides" means exactly that — not that the feature does not exist.

Two things worth doing when you see it:

- Search the documentation directly at [/docs](/docs), or press <kbd>⌘</kbd><kbd>K</kbd> anywhere in the dashboard. The search matches headings the assistant may have scored differently.
- Rephrase using the product's own words. "Publish a version" finds more than "make it live".

## Who can use it

Any role, including `viewer`. The answers come from documentation that is public anyway.

## Privacy

Conversations are scoped to you, not to your workspace. Other members — including admins and owners — cannot read them.

Questions and answers are stored so a conversation survives closing the panel. They are subject to the same data-protection controls as the rest of your workspace's data; see [Roles and permissions](/docs/platform/roles-and-permissions) for how workspace isolation works.
