"""The client, sync and async.

Both expose the same resources with the same signatures, so a codebase
moving between them changes `AgentVerse` to `AsyncAgentVerse` and adds
`await` — nothing else. They share every path and body through the pure
builders in `_internal.requests`, so the two cannot drift, and neither
inherits from the other: an `async def` overriding a `def` is not a
Liskov substitution, and buying that with a `type: ignore` on every
method is exactly the debt §16 says to refuse.

**`workspace_id` is bound once, at construction.** Every API key is
issued for exactly one workspace, so threading the id through each call
would ask the caller to repeat what their credential already fixes — and
to get it wrong in a way the server answers with a bare 404.
"""

from __future__ import annotations

import os
from types import TracebackType
from typing import Any

import httpx

from agentverse._internal import requests as build
from agentverse._internal.requests import Call
from agentverse._internal.retry import DEFAULT_MAX_RETRIES
from agentverse._internal.transport import Transport, send_async, send_sync
from agentverse.errors import ConfigurationError

#: Alias used for every list-returning signature.
#:
#: Not `list[dict[str, Any]]` written inline: several resources expose a
#: method called `list`, and inside those class bodies the bare name
#: resolves to the *method* rather than the builtin. mypy catches it; a
#: reader would not.
JsonList = list[dict[str, Any]]
StrList = list[str]

DEFAULT_BASE_URL = "https://api.agentverse.dev"
DEFAULT_TIMEOUT_SECONDS = 60.0


def _resolve(
    api_key: str | None, base_url: str | None, workspace_id: str | None
) -> tuple[str, str, str]:
    key = api_key or os.environ.get("AGENTVERSE_API_KEY")
    if not key:
        # Raised at construction, not on the first call: a missing key is
        # a deployment mistake, and it should surface at startup rather
        # than at 3am on the first request.
        raise ConfigurationError("No API key. Pass api_key=... or set AGENTVERSE_API_KEY.")
    workspace = workspace_id or os.environ.get("AGENTVERSE_WORKSPACE_ID")
    if not workspace:
        raise ConfigurationError(
            "No workspace. Pass workspace_id=... or set AGENTVERSE_WORKSPACE_ID."
        )
    url = base_url or os.environ.get("AGENTVERSE_BASE_URL") or DEFAULT_BASE_URL
    if not url.startswith(("http://", "https://")):
        raise ConfigurationError(f"base_url must be an absolute http(s) URL, got {url!r}")
    return key, url, workspace


def _as_list(result: Any) -> JsonList:
    return list(result or [])


class AgentVerse:
    """Synchronous client.

    Usable as a context manager and closable explicitly. Not closing it
    leaks a connection pool, which in a long-lived process is a slow
    file-descriptor leak rather than an obvious failure — so the context
    manager form is the documented one.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        workspace_id: str | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx.Client | None = None,
    ) -> None:
        key, url, workspace = _resolve(api_key, base_url, workspace_id)
        self.workspace_id = workspace
        self._transport = Transport(base_url=url, api_key=key, max_retries=max_retries)
        # An injected client is not ours to close: the caller may be
        # sharing one pool across several SDKs.
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout)

        self.agents = Agents(self)
        self.runs = Runs(self)
        self.marketplace = Marketplace(self)
        self.webhooks = Webhooks(self)

    def send(self, call: Call) -> Any:
        result = send_sync(
            self._client,
            self._transport,
            method=call.method,
            path=call.path,
            json_body=call.json_body,
            params=call.params,
            idempotency_key=call.idempotency_key,
        )
        return _as_list(result) if call.returns_list else result

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> AgentVerse:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


class AsyncAgentVerse:
    """Asynchronous client. Same surface as `AgentVerse`."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        workspace_id: str | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        key, url, workspace = _resolve(api_key, base_url, workspace_id)
        self.workspace_id = workspace
        self._transport = Transport(base_url=url, api_key=key, max_retries=max_retries)
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

        self.agents = AsyncAgents(self)
        self.runs = AsyncRuns(self)
        self.marketplace = AsyncMarketplace(self)
        self.webhooks = AsyncWebhooks(self)

    async def send(self, call: Call) -> Any:
        result = await send_async(
            self._client,
            self._transport,
            method=call.method,
            path=call.path,
            json_body=call.json_body,
            params=call.params,
            idempotency_key=call.idempotency_key,
        )
        return _as_list(result) if call.returns_list else result

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> AsyncAgentVerse:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()


# ---- sync resources --------------------------------------------------


class Agents:
    """Agent definitions and their versions."""

    def __init__(self, client: AgentVerse) -> None:
        self._c = client

    def list(self) -> JsonList:
        return list(self._c.send(build.list_agents(self._c.workspace_id)))

    def create(
        self,
        *,
        name: str,
        model: str,
        system_instructions: str,
        description: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        tools: StrList | None = None,
        knowledge_base_ids: StrList | None = None,
    ) -> dict[str, Any]:
        return dict(
            self._c.send(
                build.create_agent(
                    self._c.workspace_id,
                    name=name,
                    model=model,
                    system_instructions=system_instructions,
                    description=description,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    tools=tools,
                    knowledge_base_ids=knowledge_base_ids,
                )
            )
        )

    def get(self, agent_id: str) -> dict[str, Any]:
        return dict(self._c.send(build.get_agent(self._c.workspace_id, agent_id)))

    def delete(self, agent_id: str) -> None:
        self._c.send(build.delete_agent(self._c.workspace_id, agent_id))

    def publish(self, agent_id: str, *, version_id: str) -> dict[str, Any]:
        return dict(
            self._c.send(build.publish_agent(self._c.workspace_id, agent_id, version_id=version_id))
        )


class Runs:
    """Starting agent runs."""

    def __init__(self, client: AgentVerse) -> None:
        self._c = client

    def create(
        self, *, agent_id: str, input: str, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        """Submit a run. Returns immediately with a run id.

        An idempotency key is generated when none is given, because a run
        costs money and a retried POST that already arrived is how one
        charge becomes two. Supply your own when the *caller* can retry —
        a queue redelivering a job should reuse the job's id, so two
        workers cannot start the same run twice.
        """
        return dict(
            self._c.send(
                build.create_run(
                    self._c.workspace_id,
                    agent_id=agent_id,
                    input=input,
                    idempotency_key=idempotency_key,
                )
            )
        )


class Marketplace:
    """The public catalog and the first-party template library."""

    def __init__(self, client: AgentVerse) -> None:
        self._c = client

    def list_listings(self, **kwargs: Any) -> dict[str, Any]:
        return dict(self._c.send(build.list_listings(**kwargs)))

    def templates(self, *, category: str | None = None) -> JsonList:
        return list(self._c.send(build.list_templates(category=category)))

    def get(self, slug: str) -> dict[str, Any]:
        return dict(self._c.send(build.get_listing(slug)))

    def install(
        self, slug: str, *, version_number: int | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Copy a published listing into this workspace as a new agent.

        Idempotent server-side per (workspace, listing, version), so a
        repeated call returns the same agent rather than a second one.
        """
        return dict(
            self._c.send(
                build.install_listing(
                    self._c.workspace_id, slug, version_number=version_number, name=name
                )
            )
        )

    def installs(self) -> JsonList:
        return list(self._c.send(build.list_installs(self._c.workspace_id)))


class Webhooks:
    """This workspace's outbound webhook endpoints.

    Verifying an *inbound* delivery is `agentverse.webhooks.verify_webhook`
    — a free function, because a receiver has no reason to hold an API
    client or a key just to check a signature.
    """

    def __init__(self, client: AgentVerse) -> None:
        self._c = client

    def list(self) -> JsonList:
        return list(self._c.send(build.list_webhooks(self._c.workspace_id)))

    def create(self, *, url: str, events: StrList, description: str = "") -> dict[str, Any]:
        """Register an endpoint. The signing secret is in the response,
        once — store it now, it is not readable later.
        """
        return dict(
            self._c.send(
                build.create_webhook(
                    self._c.workspace_id, url=url, events=events, description=description
                )
            )
        )

    def event_types(self) -> StrList:
        return [str(name) for name in self._c.send(build.webhook_event_types(self._c.workspace_id))]

    def deliveries(self, *, endpoint_id: str | None = None, limit: int = 50) -> JsonList:
        return list(
            self._c.send(
                build.list_deliveries(self._c.workspace_id, endpoint_id=endpoint_id, limit=limit)
            )
        )

    def rotate_secret(self, endpoint_id: str) -> str:
        """A new secret, returned once. The old one stops working now."""
        result = self._c.send(build.rotate_webhook_secret(self._c.workspace_id, endpoint_id))
        return str(result["secret"])

    def delete(self, endpoint_id: str) -> None:
        self._c.send(build.delete_webhook(self._c.workspace_id, endpoint_id))


# ---- async resources -------------------------------------------------


class AsyncAgents:
    def __init__(self, client: AsyncAgentVerse) -> None:
        self._c = client

    async def list(self) -> JsonList:
        return list(await self._c.send(build.list_agents(self._c.workspace_id)))

    async def create(
        self,
        *,
        name: str,
        model: str,
        system_instructions: str,
        description: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        tools: StrList | None = None,
        knowledge_base_ids: StrList | None = None,
    ) -> dict[str, Any]:
        return dict(
            await self._c.send(
                build.create_agent(
                    self._c.workspace_id,
                    name=name,
                    model=model,
                    system_instructions=system_instructions,
                    description=description,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    tools=tools,
                    knowledge_base_ids=knowledge_base_ids,
                )
            )
        )

    async def get(self, agent_id: str) -> dict[str, Any]:
        return dict(await self._c.send(build.get_agent(self._c.workspace_id, agent_id)))

    async def delete(self, agent_id: str) -> None:
        await self._c.send(build.delete_agent(self._c.workspace_id, agent_id))

    async def publish(self, agent_id: str, *, version_id: str) -> dict[str, Any]:
        return dict(
            await self._c.send(
                build.publish_agent(self._c.workspace_id, agent_id, version_id=version_id)
            )
        )


class AsyncRuns:
    def __init__(self, client: AsyncAgentVerse) -> None:
        self._c = client

    async def create(
        self, *, agent_id: str, input: str, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        return dict(
            await self._c.send(
                build.create_run(
                    self._c.workspace_id,
                    agent_id=agent_id,
                    input=input,
                    idempotency_key=idempotency_key,
                )
            )
        )


class AsyncMarketplace:
    def __init__(self, client: AsyncAgentVerse) -> None:
        self._c = client

    async def list_listings(self, **kwargs: Any) -> dict[str, Any]:
        return dict(await self._c.send(build.list_listings(**kwargs)))

    async def templates(self, *, category: str | None = None) -> JsonList:
        return list(await self._c.send(build.list_templates(category=category)))

    async def get(self, slug: str) -> dict[str, Any]:
        return dict(await self._c.send(build.get_listing(slug)))

    async def install(
        self, slug: str, *, version_number: int | None = None, name: str | None = None
    ) -> dict[str, Any]:
        return dict(
            await self._c.send(
                build.install_listing(
                    self._c.workspace_id, slug, version_number=version_number, name=name
                )
            )
        )

    async def installs(self) -> JsonList:
        return list(await self._c.send(build.list_installs(self._c.workspace_id)))


class AsyncWebhooks:
    def __init__(self, client: AsyncAgentVerse) -> None:
        self._c = client

    async def list(self) -> JsonList:
        return list(await self._c.send(build.list_webhooks(self._c.workspace_id)))

    async def create(self, *, url: str, events: StrList, description: str = "") -> dict[str, Any]:
        return dict(
            await self._c.send(
                build.create_webhook(
                    self._c.workspace_id, url=url, events=events, description=description
                )
            )
        )

    async def event_types(self) -> StrList:
        return [
            str(name)
            for name in await self._c.send(build.webhook_event_types(self._c.workspace_id))
        ]

    async def deliveries(self, *, endpoint_id: str | None = None, limit: int = 50) -> JsonList:
        return list(
            await self._c.send(
                build.list_deliveries(self._c.workspace_id, endpoint_id=endpoint_id, limit=limit)
            )
        )

    async def rotate_secret(self, endpoint_id: str) -> str:
        result = await self._c.send(build.rotate_webhook_secret(self._c.workspace_id, endpoint_id))
        return str(result["secret"])

    async def delete(self, endpoint_id: str) -> None:
        await self._c.send(build.delete_webhook(self._c.workspace_id, endpoint_id))
