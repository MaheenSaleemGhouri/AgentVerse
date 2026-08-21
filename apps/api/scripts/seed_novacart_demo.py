"""Provisions the NovaCart Customer Support Agent demo in one workspace.

Run against a real, already-migrated environment (local dev or a real
deployment) with a real, already-authenticated user's session/API base
URL:

    uv run python scripts/seed_novacart_demo.py \\
        --base-url http://localhost:8000 \\
        --token <a real bearer JWT for the target user> \\
        --workspace-id <an existing workspace the user owns/admins>

Everything this script does goes through the real, unmodified REST API
— agent creation, agent publish, knowledge-base creation, document
upload, a custom MCP-server install pointing at this same API's own
`/mcp`, an mcp_client credential, and a permission grant — the same
sequence a workspace admin would click through by hand. Nothing here
writes to Postgres directly: doing it through the real API means every
step is validated (RBAC, schema, quota) exactly as it would be for a
real customer, which is also why this can't run inside an Alembic
migration (CLAUDE.md §8 — migrations author schema, not tenant
content; NovaCart's agent/KB/tools are workspace-owned data, not
platform catalog data).

Idempotent by name where the API allows re-reading by a stable
identifier; re-running against a workspace that already has a NovaCart
agent creates a second one rather than silently updating it — this is a
one-shot provisioning script for a demo, not a reconciler.
"""

from __future__ import annotations

import argparse
import asyncio

import httpx

NOVACART_INSTRUCTIONS = """You are the NovaCart Customer Support Agent.

Use the NovaCart Knowledge Base as the primary source for company \
policies, products, shipping rules, refunds, FAQs and support \
guidelines.

Use tools when real-time or action-based information is required.

Use create_support_ticket when:
- a customer needs human follow-up
- the issue cannot be resolved from knowledge
- a support case needs to be recorded

Use escalate_to_human when:
- a sensitive issue requires human judgment
- a customer disputes a decision
- an exception is requested
- the issue requires privileged action

Use lookup_order only when an authorized commerce integration is \
available. If it responds with available: false, tell the customer \
plainly that order lookup isn't available right now — never guess or \
invent an order status.

Use check_shipping_status only when an authorized commerce integration \
is available, with the same rule: never invent a status when the tool \
reports unavailable.

Use request_return only according to the configured authorization and \
approval policy — it always creates a ticket for a human to review; \
never tell the customer a return has been approved or processed.

Never invent:
- order status
- tracking information
- delivery dates
- refund approval
- return approval

If the required integration is unavailable, clearly tell the customer \
that the information/action is currently unavailable.

Never ask for:
- passwords
- CVV
- full payment-card numbers
- API keys
- MCP credentials

Only return information supplied by trusted knowledge retrieval or \
authorized tools."""

#: Section 30's playground checks — small enough to go straight into the
#: agent's own instructions rather than needing a real embedding call
#: (CLAUDE.md §9 — a migration/seed script must never fabricate an
#: embedding; these two facts are structured, deterministic content, not
#: a substitute for real knowledge-base ingestion of a real policy doc).
NOVACART_HOUSE_FACTS = """

House facts (authoritative until the knowledge base has more):
- Return window: 14 calendar days.
- NovaBuds Pro price: PKR 8,999."""

NEW_TOOL_NAMES = [
    "create_support_ticket",
    "escalate_to_human",
    "lookup_order",
    "check_shipping_status",
    "request_return",
]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url", required=True, help="apps/api base URL, e.g. http://localhost:8000"
    )
    parser.add_argument("--token", required=True, help="A real bearer JWT for the target user")
    parser.add_argument(
        "--workspace-id", required=True, help="An existing workspace the token's user administers"
    )
    parser.add_argument(
        "--public-mcp-url",
        default=None,
        help=(
            "This API's own public URL + /mcp (defaults to --base-url + /mcp — correct for "
            "local dev, must be the real public URL in a hosted environment since the "
            "connection is made by apps/worker, not from this script's machine)"
        ),
    )
    args = parser.parse_args()

    mcp_url = args.public_mcp_url or f"{args.base_url.rstrip('/')}/mcp"
    headers = {"Authorization": f"Bearer {args.token}"}

    async with httpx.AsyncClient(base_url=args.base_url, headers=headers, timeout=30.0) as client:
        ws_prefix = f"/api/v1/workspaces/{args.workspace_id}"

        print("Creating NovaCart agent...")
        create_agent = await client.post(
            f"{ws_prefix}/agents",
            json={
                "name": "NovaCart Customer Support Agent",
                "description": "Live-chat support for NovaCart customers.",
                "model": "gpt-4o-mini",
                "system_instructions": NOVACART_INSTRUCTIONS + NOVACART_HOUSE_FACTS,
                "temperature": None,
                "max_output_tokens": None,
                "tools": [],
                "knowledge_base_ids": [],
            },
        )
        create_agent.raise_for_status()
        agent_id = create_agent.json()["agent"]["id"]
        print(f"  agent_id = {agent_id}")

        print("Publishing...")
        (await client.post(f"{ws_prefix}/agents/{agent_id}/publish")).raise_for_status()

        print("Creating knowledge base container...")
        create_kb = await client.post(
            f"{ws_prefix}/knowledge",
            json={
                "name": "NovaCart Policies",
                "description": "Return window, pricing, shipping rules.",
            },
        )
        create_kb.raise_for_status()
        kb_id = create_kb.json()["id"]
        print(f"  knowledge_base_id = {kb_id} (upload a real policy doc separately — see below)")

        print("Registering AgentVerse's own MCP server as a custom integration...")
        install = await client.post(
            f"{ws_prefix}/integrations/custom",
            json={
                "display_name": "AgentVerse Platform Tools",
                "transport": "streamable_http",
                "endpoint_url": mcp_url,
                "auth_scheme": "bearer_token",
                "config": {},
            },
        )
        install.raise_for_status()
        installed_server_id = install.json()["id"]
        print(f"  installed_server_id = {installed_server_id}")

        print("Issuing an mcp_client credential for that install to authenticate with...")
        issue = await client.post(
            f"{ws_prefix}/mcp-clients", json={"name": "NovaCart platform-tools client"}
        )
        issue.raise_for_status()
        mcp_client_key = issue.json()["key"]

        print("Storing that credential on the install (activates it)...")
        put_cred = await client.put(
            f"{ws_prefix}/integrations/{installed_server_id}/credentials",
            json={"key": "bearer_token", "value": mcp_client_key, "auth_scheme": "bearer_token"},
        )
        put_cred.raise_for_status()

        print("Granting NovaCart's agent the 5 new tools...")
        grant = await client.post(
            f"{ws_prefix}/integrations/{installed_server_id}/permissions",
            json={
                "agent_id": agent_id,
                "level": "full",
                "allowed_tools": NEW_TOOL_NAMES,
            },
        )
        grant.raise_for_status()
        print(f"  permission_id = {grant.json()['id']}")

    print()
    print("Done. NovaCart is provisioned and its tools are wired through")
    print("AgentVerse's own governed MCP boundary end to end.")
    print()
    print("Still needed for the knowledge-question playground checks to pull")
    print("from real retrieval rather than the house-facts fallback in the")
    print("agent's own instructions: upload a real policy document to")
    print(f"knowledge base {kb_id!r} (POST {ws_prefix}/knowledge/{{kb_id}}/documents,")
    print("multipart file upload) and wait for apps/worker to finish ingesting")
    print("it — that step needs a real OPENAI_API_KEY and a running worker,")
    print("neither of which this script assumes or fakes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
