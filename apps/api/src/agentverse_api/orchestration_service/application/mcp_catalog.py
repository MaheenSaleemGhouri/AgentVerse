"""The seeded MCP server catalog.

Adding support for a service is a **row here**, not a module. That is the
whole reason this phase builds on MCP rather than writing per-provider
connectors (ADR-0010).

## On `availability`, which is the honest part

Every entry declares whether a server actually exists to install:

- `official` — the vendor publishes and maintains an MCP server.
- `community` — a third-party server exists; useful, but nobody is
  contractually on the hook for it.
- `custom_required` — **no MCP server exists today.** The entry is
  browsable and documented so a user can see the service is understood,
  but Install is disabled and the card says why.

That last value is why this file is longer than a dict of names. Several
services people expect to see have no MCP server at present. Seeding them
as installable would produce a marketplace that lies: a user clicks
Install, enters a credential, and gets a connection that can never
succeed. Saying "no server available yet — register your own endpoint" is
worse marketing and better software.

## On `command` for stdio entries

The command and args below are the *only* source of a stdio command. A
user-supplied command would be arbitrary code execution on the worker
fleet, so `factory._build_stdio` refuses anything not catalog-backed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """One row of the seeded catalog.

    A plain dataclass rather than an ORM object so the catalog can be
    read, diffed, and tested without a database — seeding is idempotent
    and runs against this list.
    """

    slug: str
    name: str
    description: str
    category: str
    transport: str
    availability: str
    auth_scheme: str
    command: str | None = None
    command_args: tuple[str, ...] = ()
    endpoint_url: str | None = None
    required_credentials: tuple[str, ...] = ()
    oauth_scopes: tuple[str, ...] = ()
    documentation_url: str | None = None
    icon_slug: str | None = None
    #: Shown on a `custom_required` card so the user knows what to do
    #: instead of wondering why Install is greyed out.
    unavailable_reason: str | None = None


def _npx(package: str) -> tuple[str, tuple[str, ...]]:
    """Standard stdio invocation for a published npm MCP server.

    `-y` so the first run does not block on an install prompt no one is
    there to answer.
    """
    return "npx", ("-y", package)


_DEV_TOOLS: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        slug="github",
        name="GitHub",
        description=(
            "Read and manage repositories, issues, pull requests, and code search. "
            "Use for anything involving a GitHub repository's contents or activity."
        ),
        category="Developer tools",
        transport="stdio",
        availability="official",
        auth_scheme="api_key",
        command=_npx("@modelcontextprotocol/server-github")[0],
        command_args=_npx("@modelcontextprotocol/server-github")[1],
        required_credentials=("GITHUB_PERSONAL_ACCESS_TOKEN",),
        documentation_url="https://github.com/modelcontextprotocol/servers/tree/main/src/github",
        icon_slug="github",
    ),
    CatalogEntry(
        slug="gitlab",
        name="GitLab",
        description=(
            "Read and manage GitLab projects, issues, and merge requests. "
            "Use for repositories hosted on GitLab rather than GitHub."
        ),
        category="Developer tools",
        transport="stdio",
        availability="official",
        auth_scheme="api_key",
        command=_npx("@modelcontextprotocol/server-gitlab")[0],
        command_args=_npx("@modelcontextprotocol/server-gitlab")[1],
        required_credentials=("GITLAB_PERSONAL_ACCESS_TOKEN",),
        documentation_url="https://github.com/modelcontextprotocol/servers/tree/main/src/gitlab",
        icon_slug="gitlab",
    ),
    CatalogEntry(
        slug="docker",
        name="Docker",
        description=(
            "Inspect and manage containers, images, and compose stacks on a Docker host. "
            "Use for container status, logs, and lifecycle operations."
        ),
        category="Infrastructure",
        transport="stdio",
        availability="community",
        auth_scheme="none",
        command=_npx("docker-mcp")[0],
        command_args=_npx("docker-mcp")[1],
        documentation_url="https://github.com/QuantGeekDev/docker-mcp",
        icon_slug="docker",
    ),
    CatalogEntry(
        slug="kubernetes",
        name="Kubernetes",
        description=(
            "Query and manage Kubernetes resources: pods, deployments, services, and logs. "
            "Use for cluster state and troubleshooting."
        ),
        category="Infrastructure",
        transport="stdio",
        availability="community",
        auth_scheme="none",
        command=_npx("mcp-server-kubernetes")[0],
        command_args=_npx("mcp-server-kubernetes")[1],
        documentation_url="https://github.com/Flux159/mcp-server-kubernetes",
        icon_slug="kubernetes",
    ),
)

_COMMUNICATION: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        slug="slack",
        name="Slack",
        description=(
            "Read channel history, post messages, and look up users in a Slack workspace. "
            "Use for team communication and channel search."
        ),
        category="Communication",
        transport="stdio",
        availability="official",
        auth_scheme="api_key",
        command=_npx("@modelcontextprotocol/server-slack")[0],
        command_args=_npx("@modelcontextprotocol/server-slack")[1],
        required_credentials=("SLACK_BOT_TOKEN", "SLACK_TEAM_ID"),
        documentation_url="https://github.com/modelcontextprotocol/servers/tree/main/src/slack",
        icon_slug="slack",
    ),
    CatalogEntry(
        slug="discord",
        name="Discord",
        description=(
            "Read and send messages across Discord channels and threads. "
            "Use for community servers and bot-driven workflows."
        ),
        category="Communication",
        transport="stdio",
        availability="community",
        auth_scheme="api_key",
        command=_npx("mcp-discord")[0],
        command_args=_npx("mcp-discord")[1],
        required_credentials=("DISCORD_TOKEN",),
        documentation_url="https://github.com/v-3/discordmcp",
        icon_slug="discord",
    ),
    CatalogEntry(
        slug="telegram",
        name="Telegram",
        description=(
            "Send and read Telegram messages via a bot. "
            "Use for notifications and lightweight chat automation."
        ),
        category="Communication",
        transport="stdio",
        availability="community",
        auth_scheme="api_key",
        command=_npx("mcp-telegram")[0],
        command_args=_npx("mcp-telegram")[1],
        required_credentials=("TELEGRAM_BOT_TOKEN",),
        icon_slug="telegram",
    ),
    CatalogEntry(
        slug="whatsapp",
        name="WhatsApp",
        description=(
            "Send and receive WhatsApp Business messages. "
            "Would be used for customer conversations and notifications."
        ),
        category="Communication",
        transport="streamable_http",
        availability="custom_required",
        auth_scheme="bearer_token",
        unavailable_reason=(
            "Meta does not publish an MCP server for the WhatsApp Business API. "
            "Register your own MCP endpoint that wraps the Cloud API, then connect it here."
        ),
        documentation_url="https://developers.facebook.com/docs/whatsapp/cloud-api",
        icon_slug="whatsapp",
    ),
    CatalogEntry(
        slug="twilio",
        name="Twilio",
        description=(
            "Send SMS and place voice calls through Twilio. "
            "Would be used for programmable messaging workflows."
        ),
        category="Communication",
        transport="streamable_http",
        availability="custom_required",
        auth_scheme="basic",
        unavailable_reason=(
            "Twilio does not publish a first-party MCP server. Wrap the REST API in your "
            "own MCP endpoint and register it as a custom server."
        ),
        documentation_url="https://www.twilio.com/docs/usage/api",
        icon_slug="twilio",
    ),
)

_PRODUCTIVITY: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        slug="notion",
        name="Notion",
        description=(
            "Search, read, and update Notion pages and databases. "
            "Use for team wikis, specs, and structured notes."
        ),
        category="Productivity",
        transport="streamable_http",
        availability="official",
        auth_scheme="oauth2",
        endpoint_url="https://mcp.notion.com/mcp",
        oauth_scopes=(),
        documentation_url="https://developers.notion.com/docs/mcp",
        icon_slug="notion",
    ),
    CatalogEntry(
        slug="linear",
        name="Linear",
        description=(
            "Read and manage Linear issues, projects, and cycles. "
            "Use for engineering issue tracking and sprint state."
        ),
        category="Productivity",
        transport="streamable_http",
        availability="official",
        auth_scheme="oauth2",
        endpoint_url="https://mcp.linear.app/mcp",
        documentation_url="https://linear.app/docs/mcp",
        icon_slug="linear",
    ),
    CatalogEntry(
        slug="google-drive",
        name="Google Drive",
        description=(
            "Search and read files stored in Google Drive. "
            "Use for retrieving documents by name or content."
        ),
        category="Productivity",
        transport="stdio",
        availability="official",
        auth_scheme="oauth2",
        command=_npx("@modelcontextprotocol/server-gdrive")[0],
        command_args=_npx("@modelcontextprotocol/server-gdrive")[1],
        oauth_scopes=("https://www.googleapis.com/auth/drive.readonly",),
        documentation_url="https://github.com/modelcontextprotocol/servers/tree/main/src/gdrive",
        icon_slug="googledrive",
    ),
    CatalogEntry(
        slug="google-calendar",
        name="Google Calendar",
        description=(
            "Read and create calendar events, and check availability. "
            "Use for scheduling and agenda questions."
        ),
        category="Productivity",
        transport="stdio",
        availability="community",
        auth_scheme="oauth2",
        command=_npx("@cocal/google-calendar-mcp")[0],
        command_args=_npx("@cocal/google-calendar-mcp")[1],
        oauth_scopes=("https://www.googleapis.com/auth/calendar",),
        icon_slug="googlecalendar",
    ),
    CatalogEntry(
        slug="gmail",
        name="Gmail",
        description=(
            "Search, read, and send email through Gmail. Use for inbox triage and drafting replies."
        ),
        category="Productivity",
        transport="stdio",
        availability="community",
        auth_scheme="oauth2",
        command=_npx("@gongrzhe/server-gmail-autoauth-mcp")[0],
        command_args=_npx("@gongrzhe/server-gmail-autoauth-mcp")[1],
        oauth_scopes=("https://www.googleapis.com/auth/gmail.modify",),
        icon_slug="gmail",
    ),
    CatalogEntry(
        slug="google-docs",
        name="Google Docs",
        description=(
            "Read and edit Google Docs documents. Would be used for drafting and "
            "reviewing long-form content."
        ),
        category="Productivity",
        transport="stdio",
        availability="custom_required",
        auth_scheme="oauth2",
        unavailable_reason=(
            "No maintained standalone MCP server for Docs. The Google Drive server covers "
            "reading Docs content; use it, or register your own endpoint for editing."
        ),
        icon_slug="googledocs",
    ),
    CatalogEntry(
        slug="google-sheets",
        name="Google Sheets",
        description=(
            "Read and write spreadsheet data. Would be used for reporting and "
            "structured data the team keeps in Sheets."
        ),
        category="Productivity",
        transport="stdio",
        availability="community",
        auth_scheme="oauth2",
        command=_npx("@mkummer225/google-sheets-mcp")[0],
        command_args=_npx("@mkummer225/google-sheets-mcp")[1],
        oauth_scopes=("https://www.googleapis.com/auth/spreadsheets",),
        icon_slug="googlesheets",
    ),
    CatalogEntry(
        slug="jira",
        name="Jira",
        description=(
            "Read and manage Jira issues, sprints, and boards. "
            "Use for project tracking in Atlassian-based teams."
        ),
        category="Productivity",
        transport="streamable_http",
        availability="official",
        auth_scheme="oauth2",
        endpoint_url="https://mcp.atlassian.com/v1/sse",
        documentation_url="https://support.atlassian.com/atlassian-rovo-mcp-server/",
        icon_slug="jira",
    ),
    CatalogEntry(
        slug="confluence",
        name="Confluence",
        description=(
            "Search and read Confluence spaces and pages. "
            "Use for internal documentation and runbooks."
        ),
        category="Productivity",
        transport="streamable_http",
        availability="official",
        auth_scheme="oauth2",
        endpoint_url="https://mcp.atlassian.com/v1/sse",
        documentation_url="https://support.atlassian.com/atlassian-rovo-mcp-server/",
        icon_slug="confluence",
    ),
    CatalogEntry(
        slug="clickup",
        name="ClickUp",
        description=(
            "Read and manage ClickUp tasks, lists, and spaces. "
            "Use for task tracking in ClickUp workspaces."
        ),
        category="Productivity",
        transport="stdio",
        availability="community",
        auth_scheme="api_key",
        command=_npx("@taazkareem/clickup-mcp-server")[0],
        command_args=_npx("@taazkareem/clickup-mcp-server")[1],
        required_credentials=("CLICKUP_API_KEY", "CLICKUP_TEAM_ID"),
        icon_slug="clickup",
    ),
    CatalogEntry(
        slug="trello",
        name="Trello",
        description=(
            "Read and manage Trello boards, lists, and cards. Use for lightweight kanban workflows."
        ),
        category="Productivity",
        transport="stdio",
        availability="community",
        auth_scheme="api_key",
        command=_npx("@delorenj/mcp-server-trello")[0],
        command_args=_npx("@delorenj/mcp-server-trello")[1],
        required_credentials=("TRELLO_API_KEY", "TRELLO_TOKEN"),
        icon_slug="trello",
    ),
    CatalogEntry(
        slug="airtable",
        name="Airtable",
        description=(
            "Read and write Airtable bases, tables, and records. "
            "Use for structured operational data."
        ),
        category="Productivity",
        transport="stdio",
        availability="community",
        auth_scheme="api_key",
        command=_npx("airtable-mcp-server")[0],
        command_args=_npx("airtable-mcp-server")[1],
        required_credentials=("AIRTABLE_API_KEY",),
        icon_slug="airtable",
    ),
    CatalogEntry(
        slug="microsoft-teams",
        name="Microsoft Teams",
        description=(
            "Read and post Teams messages and channel content. "
            "Would be used for Microsoft-centric team communication."
        ),
        category="Communication",
        transport="streamable_http",
        availability="custom_required",
        auth_scheme="oauth2",
        unavailable_reason=(
            "Microsoft does not publish a general-purpose Teams MCP server. Wrap Microsoft "
            "Graph in your own MCP endpoint and register it as a custom server."
        ),
        documentation_url="https://learn.microsoft.com/graph/api/resources/teams-api-overview",
        icon_slug="microsoftteams",
    ),
    CatalogEntry(
        slug="outlook",
        name="Microsoft Outlook",
        description=(
            "Read and send Outlook mail and calendar events. "
            "Would be used for Microsoft 365 mailboxes."
        ),
        category="Productivity",
        transport="streamable_http",
        availability="custom_required",
        auth_scheme="oauth2",
        unavailable_reason=(
            "No first-party Outlook MCP server. Wrap Microsoft Graph in your own MCP "
            "endpoint and register it as a custom server."
        ),
        documentation_url="https://learn.microsoft.com/graph/outlook-mail-concept-overview",
        icon_slug="microsoftoutlook",
    ),
    CatalogEntry(
        slug="dropbox",
        name="Dropbox",
        description=(
            "Search and read files in Dropbox. Would be used for documents stored "
            "outside Google Drive."
        ),
        category="Productivity",
        transport="stdio",
        availability="custom_required",
        auth_scheme="oauth2",
        unavailable_reason=(
            "Dropbox does not publish an MCP server. Register your own endpoint wrapping "
            "the Dropbox API."
        ),
        icon_slug="dropbox",
    ),
    CatalogEntry(
        slug="onedrive",
        name="OneDrive",
        description=(
            "Search and read files in OneDrive. Would be used for Microsoft 365 file storage."
        ),
        category="Productivity",
        transport="streamable_http",
        availability="custom_required",
        auth_scheme="oauth2",
        unavailable_reason=(
            "No first-party OneDrive MCP server. Wrap Microsoft Graph in your own MCP "
            "endpoint and register it as a custom server."
        ),
        icon_slug="onedrive",
    ),
)

_BUSINESS: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        slug="stripe",
        name="Stripe",
        description=(
            "Query customers, subscriptions, invoices, and payments in Stripe. "
            "Use for billing questions and revenue lookups."
        ),
        category="Business",
        transport="streamable_http",
        availability="official",
        auth_scheme="bearer_token",
        endpoint_url="https://mcp.stripe.com",
        required_credentials=("STRIPE_SECRET_KEY",),
        documentation_url="https://docs.stripe.com/mcp",
        icon_slug="stripe",
    ),
    CatalogEntry(
        slug="hubspot",
        name="HubSpot",
        description=(
            "Read and update CRM contacts, companies, and deals in HubSpot. "
            "Use for sales pipeline and customer record questions."
        ),
        category="Business",
        transport="streamable_http",
        availability="official",
        auth_scheme="oauth2",
        endpoint_url="https://mcp.hubspot.com/anthropic",
        documentation_url="https://developers.hubspot.com/mcp",
        icon_slug="hubspot",
    ),
    CatalogEntry(
        slug="shopify",
        name="Shopify",
        description=(
            "Query products, orders, and customers in a Shopify store. "
            "Use for commerce operations and order lookups."
        ),
        category="Business",
        transport="streamable_http",
        availability="official",
        auth_scheme="bearer_token",
        endpoint_url="https://mcp.shopify.com/mcp",
        required_credentials=("SHOPIFY_ACCESS_TOKEN",),
        documentation_url="https://shopify.dev/docs/apps/build/storefront-mcp",
        icon_slug="shopify",
    ),
    CatalogEntry(
        slug="salesforce",
        name="Salesforce",
        description=(
            "Query and update Salesforce CRM objects. Would be used for enterprise "
            "sales pipeline data."
        ),
        category="Business",
        transport="streamable_http",
        availability="custom_required",
        auth_scheme="oauth2",
        unavailable_reason=(
            "Salesforce does not publish a general-purpose MCP server. Wrap the REST API "
            "in your own MCP endpoint and register it as a custom server."
        ),
        documentation_url="https://developer.salesforce.com/docs/apis",
        icon_slug="salesforce",
    ),
)

_DATA: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        slug="postgresql",
        name="PostgreSQL",
        description=(
            "Run read-only SQL queries and inspect schemas in a PostgreSQL database. "
            "Use for analytical questions against your own data."
        ),
        category="Data",
        transport="stdio",
        availability="official",
        auth_scheme="api_key",
        command=_npx("@modelcontextprotocol/server-postgres")[0],
        command_args=_npx("@modelcontextprotocol/server-postgres")[1],
        required_credentials=("POSTGRES_CONNECTION_STRING",),
        documentation_url="https://github.com/modelcontextprotocol/servers/tree/main/src/postgres",
        icon_slug="postgresql",
    ),
    CatalogEntry(
        slug="mysql",
        name="MySQL",
        description=(
            "Run SQL queries and inspect schemas in a MySQL database. "
            "Use for analytical questions against MySQL-hosted data."
        ),
        category="Data",
        transport="stdio",
        availability="community",
        auth_scheme="api_key",
        command=_npx("@benborla29/mcp-server-mysql")[0],
        command_args=_npx("@benborla29/mcp-server-mysql")[1],
        required_credentials=("MYSQL_CONNECTION_STRING",),
        icon_slug="mysql",
    ),
    CatalogEntry(
        slug="redis",
        name="Redis",
        description=(
            "Inspect and manipulate Redis keys, hashes, and streams. "
            "Use for cache inspection and queue state."
        ),
        category="Data",
        transport="stdio",
        availability="official",
        auth_scheme="api_key",
        command=_npx("@modelcontextprotocol/server-redis")[0],
        command_args=_npx("@modelcontextprotocol/server-redis")[1],
        required_credentials=("REDIS_URL",),
        documentation_url="https://github.com/modelcontextprotocol/servers/tree/main/src/redis",
        icon_slug="redis",
    ),
    CatalogEntry(
        slug="qdrant",
        name="Qdrant",
        description=(
            "Store and search vectors in a Qdrant collection. "
            "Use for semantic memory outside AgentVerse's own knowledge bases."
        ),
        category="Data",
        transport="stdio",
        availability="official",
        auth_scheme="api_key",
        command="uvx",
        command_args=("mcp-server-qdrant",),
        required_credentials=("QDRANT_URL", "QDRANT_API_KEY"),
        documentation_url="https://github.com/qdrant/mcp-server-qdrant",
        icon_slug="qdrant",
    ),
    CatalogEntry(
        slug="supabase",
        name="Supabase",
        description=(
            "Query Supabase tables, manage schemas, and inspect project configuration. "
            "Use for Supabase-hosted application data."
        ),
        category="Data",
        transport="stdio",
        availability="official",
        auth_scheme="api_key",
        command=_npx("@supabase/mcp-server-supabase@latest")[0],
        command_args=_npx("@supabase/mcp-server-supabase@latest")[1],
        required_credentials=("SUPABASE_ACCESS_TOKEN",),
        documentation_url="https://supabase.com/docs/guides/getting-started/mcp",
        icon_slug="supabase",
    ),
)

_CLOUD: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        slug="aws",
        name="AWS",
        description=(
            "Query AWS resources and documentation across services. "
            "Use for cloud inventory and configuration questions."
        ),
        category="Cloud",
        transport="stdio",
        availability="official",
        auth_scheme="api_key",
        command="uvx",
        command_args=("awslabs.core-mcp-server@latest",),
        required_credentials=("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"),
        documentation_url="https://github.com/awslabs/mcp",
        icon_slug="amazonaws",
    ),
    CatalogEntry(
        slug="cloudflare",
        name="Cloudflare",
        description=(
            "Manage Cloudflare zones, DNS, Workers, and analytics. "
            "Use for edge configuration and traffic questions."
        ),
        category="Cloud",
        transport="streamable_http",
        availability="official",
        auth_scheme="oauth2",
        endpoint_url="https://observability.mcp.cloudflare.com/mcp",
        documentation_url="https://developers.cloudflare.com/agents/model-context-protocol/",
        icon_slug="cloudflare",
    ),
    CatalogEntry(
        slug="azure",
        name="Microsoft Azure",
        description=(
            "Query Azure resources, resource groups, and configuration. "
            "Use for Azure cloud inventory questions."
        ),
        category="Cloud",
        transport="stdio",
        availability="official",
        auth_scheme="api_key",
        command=_npx("@azure/mcp@latest")[0],
        command_args=("-y", "@azure/mcp@latest", "server", "start"),
        required_credentials=("AZURE_SUBSCRIPTION_ID",),
        documentation_url="https://github.com/Azure/azure-mcp",
        icon_slug="microsoftazure",
    ),
    CatalogEntry(
        slug="google-cloud",
        name="Google Cloud",
        description=(
            "Query Google Cloud resources and configuration. Would be used for GCP "
            "inventory and operations."
        ),
        category="Cloud",
        transport="stdio",
        availability="custom_required",
        auth_scheme="oauth2",
        unavailable_reason=(
            "Google publishes MCP servers for individual GCP products rather than one "
            "general server. Register the specific product's endpoint as a custom server."
        ),
        documentation_url="https://cloud.google.com/products",
        icon_slug="googlecloud",
    ),
)

#: The full seeded catalog. Ordered by category for a stable, readable
#: marketplace listing before any user-chosen sort is applied.
CATALOG: tuple[CatalogEntry, ...] = (
    *_DEV_TOOLS,
    *_COMMUNICATION,
    *_PRODUCTIVITY,
    *_BUSINESS,
    *_DATA,
    *_CLOUD,
)


def catalog_by_slug() -> dict[str, CatalogEntry]:
    return {entry.slug: entry for entry in CATALOG}


def validate_catalog() -> list[str]:
    """Returns the catalog's internal contradictions, or an empty list.

    Run as a test rather than at import: a malformed entry should fail
    CI, not a production boot. The rules encode the security invariants
    that a hand-edited row is most likely to break.
    """
    problems: list[str] = []
    seen: set[str] = set()

    for entry in CATALOG:
        if entry.slug in seen:
            problems.append(f"{entry.slug}: duplicate slug")
        seen.add(entry.slug)

        if entry.transport not in ("stdio", "sse", "streamable_http"):
            problems.append(f"{entry.slug}: unknown transport {entry.transport!r}")
        if entry.availability not in ("official", "community", "custom_required"):
            problems.append(f"{entry.slug}: unknown availability {entry.availability!r}")

        installable = entry.availability != "custom_required"

        # An installable stdio entry without a command cannot start, and
        # the command may only ever come from here.
        if installable and entry.transport == "stdio" and not entry.command:
            problems.append(f"{entry.slug}: installable stdio entry has no command")
        # An installable HTTP entry without an endpoint has nothing to
        # connect to — the exact "marketplace that lies" failure.
        if installable and entry.transport in ("sse", "streamable_http") and not entry.endpoint_url:
            problems.append(f"{entry.slug}: installable HTTP entry has no endpoint_url")
        # A card that cannot be installed must say why.
        if not installable and not entry.unavailable_reason:
            problems.append(f"{entry.slug}: custom_required entry has no unavailable_reason")
        # A tool description is part of the prompt; a thin one degrades
        # tool selection as much as a bad system prompt (`mcp-expert`).
        if len(entry.description) < 40:
            problems.append(f"{entry.slug}: description is too thin for reliable tool selection")

    return problems
