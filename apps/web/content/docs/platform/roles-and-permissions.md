---
title: Roles and permissions
summary: What each workspace role can do, how workspaces isolate data, and how organizations group them.
pillar: platform
last_verified: "2026-08-07"
status: published
order: 3
---

A workspace is the unit of isolation in AgentVerse. Everything — agents, runs, knowledge bases, keys, billing — belongs to exactly one, and nothing crosses between them.

## The four roles

Roles are a strict hierarchy: each includes everything below it.

| Role | Can |
| --- | --- |
| `viewer` | Read agents, runs, traces, and knowledge bases. |
| `member` | Everything above, plus create and edit agents, upload documents, and trigger runs. |
| `admin` | Everything above, plus manage members, issue and revoke API keys, connect integrations, publish listings, and read audit logs. |
| `owner` | Everything above, plus billing, workspace deletion, and transferring ownership. |

Access is deny-by-default and enforced on the server. A control the interface hides is also refused by the API — hiding a button is a courtesy, never the enforcement.

A workspace always has at least one owner. The last owner cannot leave or be demoted; transfer ownership first.

## Cross-workspace requests answer 404

Asking for a resource in a workspace you are not a member of returns `404`, not `403`. This is deliberate: `403` would confirm the resource exists, which lets someone map another tenant's contents by probing ids. Inside a workspace, a permission you lack does return `403` — there, the resource's existence is not a secret.

If the API returns `404` for something you can see in the dashboard, check which workspace your API key belongs to.

## Resource permissions

Beyond roles, specific permissions can be granted on specific resources — letting a `member` manage billing, for example, without making them an admin. These compose with roles rather than replacing them: the role sets the floor, the grant adds on top. Grants and revocations are recorded in the audit log.

## API key scope

An API key's effective permissions are the intersection of the key's own scope and the role of the identity that issued it. A read-only key issued by an owner is still read-only; a full-access key issued by a member cannot exceed what a member can do.

## Organizations

An organization groups several workspaces for billing and SSO. It is a grouping layer, not an access layer: **attaching a workspace to an organization grants nobody any access to it.** Workspace membership stays the only thing that decides who can read a workspace's data — an organization owner with no membership in one of its workspaces cannot open it.

Deleting an organization detaches its workspaces; it never deletes them.

## Audit logs

Sign-ins, permission grants and denials on sensitive actions, and destructive operations are written to an append-only log. It cannot be edited or deleted, including by an owner. `admin` or higher to read; filter by actor, action, and date under **Audit logs**.

## Troubleshooting

**A member cannot publish a listing.** Publishing is `admin` — it is a public act on behalf of the workspace.

**The last owner cannot leave.** Transfer ownership first.

**An API key gets `403` where the dashboard works.** The key's scope, or the role of whoever issued it. The effective permission is the intersection.

## Related guides

- [API keys and the SDKs](/docs/platform/api-keys-and-sdks)
- [Publish a listing](/docs/marketplace/publish-a-listing)
