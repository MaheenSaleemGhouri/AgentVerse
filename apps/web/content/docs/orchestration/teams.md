---
title: Build a team of agents
summary: Compose several agents into a supervisor-and-specialists team that hands work between them.
pillar: orchestration
last_verified: "2026-08-07"
status: published
order: 2
---

A team is several agents working on one task, with a defined shape for how work moves between them. Use one when a task genuinely decomposes — research then write, draft then review — not because more agents sounds better.

## Prerequisites

- At least two published agents.
- `member` or higher.

## Start with one agent

The simplest topology that works is the right one. A single agent with the right tools beats a three-agent team for most tasks, and it is far easier to debug: one set of instructions, one trace, one place a mistake can come from.

Reach for a team when the task has genuinely separable parts, or when you want one agent to check another's work.

## Topologies

**Supervisor and specialists.** A supervisor agent decides which specialist handles what, and assembles the result. The common shape, and the one to start with.

**Sequential handoff.** Each agent does its part and passes the work along. Good when the stages are fixed and ordered.

## Set one up

1. Open **AI teams** in the sidebar.
2. Create a team and choose its topology.
3. Add member agents and give each one a handoff description.

The handoff description is what the supervisor reads when deciding where to send work. Treat it as a prompt, because it is one: "handles billing questions, including refunds and proration" routes correctly; "billing stuff" does not.

## What crosses a handoff

A handoff carries a structured payload — a summary and pointers such as a run id — not a raw transcript dump. One agent never silently rewrites another's context. This is why a team trace is readable: each handoff records what was actually passed.

## Bounds

Every team run has enforced ceilings on steps, cost, and wall-clock time. All three matter: a run that stays under its step limit can still be a cost incident if each step is expensive, and a run that stays under both can still hang. When a run hits a ceiling it stops and the trace says which one.

## Expected result

A run whose trace shows the supervisor's routing decisions, each specialist's work nested underneath, and the handoffs between them.

## Troubleshooting

**Work goes to the wrong specialist.** The handoff descriptions. Make them concrete and non-overlapping.

**The team loops between two agents.** Usually neither has instructions that say when it is finished. Give each specialist an explicit completion condition. The step ceiling stops the loop, but it stops it by failing the run, which is a backstop and not a fix.

**It costs more than the same work by one agent.** It will. Every handoff re-sends context to another model call. That is the price of decomposition, and it is only worth paying when decomposition genuinely improves the output.

## Related guides

- [Run an agent from your own code](/docs/orchestration/running-agents)
- [Read a run's trace](/docs/observability/watch-a-run)
