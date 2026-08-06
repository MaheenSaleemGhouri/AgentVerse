"""What each operation sends, as data.

The sync and async clients differ only in `await`. Sharing the *paths*
and *bodies* through pure builders means neither can drift from the
other, without the async resources inheriting from the sync ones —
which needs a `type: ignore` on every overridden method, because an
`async def` overriding a `def` is not a Liskov substitution and mypy is
right to say so.

Each builder returns a `Call`: everything the transport needs and
nothing about how it is dispatched.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Call:
    method: str
    path: str
    json_body: Any = None
    params: dict[str, Any] | None = None
    idempotency_key: str | None = None
    #: Set where the endpoint returns a list; the clients use it to
    #: normalise `None` (an empty 204-ish body) into `[]` rather than
    #: handing the caller a `None` to guard.
    returns_list: bool = False


def workspace_path(workspace_id: str, suffix: str) -> str:
    return f"/api/v1/workspaces/{workspace_id}{suffix}"


def _present(**values: Any) -> dict[str, Any]:
    """Drop `None`s.

    Absent and null are different to this API: absent means "use the
    default", null would mean "set it to nothing". Sending null for an
    omitted argument changes the request's meaning.
    """
    return {key: value for key, value in values.items() if value is not None}


# ---- agents ----------------------------------------------------------


def list_agents(workspace_id: str) -> Call:
    return Call("GET", workspace_path(workspace_id, "/agents"), returns_list=True)


def create_agent(
    workspace_id: str,
    *,
    name: str,
    model: str,
    system_instructions: str,
    description: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    tools: list[str] | None = None,
    knowledge_base_ids: list[str] | None = None,
) -> Call:
    body = {"name": name, "model": model, "system_instructions": system_instructions}
    body.update(
        _present(
            description=description,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            tools=tools,
            knowledge_base_ids=knowledge_base_ids,
        )
    )
    return Call("POST", workspace_path(workspace_id, "/agents"), json_body=body)


def get_agent(workspace_id: str, agent_id: str) -> Call:
    return Call("GET", workspace_path(workspace_id, f"/agents/{agent_id}"))


def delete_agent(workspace_id: str, agent_id: str) -> Call:
    return Call("DELETE", workspace_path(workspace_id, f"/agents/{agent_id}"))


def publish_agent(workspace_id: str, agent_id: str, *, version_id: str) -> Call:
    return Call(
        "POST",
        workspace_path(workspace_id, f"/agents/{agent_id}/publish"),
        json_body={"version_id": version_id},
    )


# ---- runs ------------------------------------------------------------


def create_run(
    workspace_id: str, *, agent_id: str, input: str, idempotency_key: str | None = None
) -> Call:
    """A run submission always carries an idempotency key.

    Generated when the caller does not supply one, because a run costs
    money and a retried POST that already arrived is how one charge
    becomes two. Supplying your own matters when the *caller* can retry:
    a queue redelivering a job should reuse the job's id so two workers
    cannot start the same run twice.
    """
    return Call(
        "POST",
        workspace_path(workspace_id, f"/agents/{agent_id}/runs"),
        json_body={"input": input},
        idempotency_key=idempotency_key or str(uuid.uuid4()),
    )


# ---- marketplace -----------------------------------------------------


def list_listings(
    *,
    category: str | None = None,
    query: str | None = None,
    free_only: bool = False,
    official: bool | None = None,
    sort: str = "popular",
    limit: int = 24,
    offset: int = 0,
) -> Call:
    params: dict[str, Any] = {"sort": sort, "limit": limit, "offset": offset}
    params.update(_present(category=category, q=query, official=official))
    if free_only:
        params["free"] = True
    return Call("GET", "/api/v1/marketplace/listings", params=params)


def list_templates(*, category: str | None = None) -> Call:
    return Call(
        "GET",
        "/api/v1/marketplace/templates",
        params=_present(category=category) or None,
        returns_list=True,
    )


def get_listing(slug: str) -> Call:
    return Call("GET", f"/api/v1/marketplace/listings/{slug}")


def install_listing(
    workspace_id: str, slug: str, *, version_number: int | None = None, name: str | None = None
) -> Call:
    return Call(
        "POST",
        workspace_path(workspace_id, f"/marketplace/listings/{slug}/install"),
        json_body=_present(version_number=version_number, name=name),
    )


def list_installs(workspace_id: str) -> Call:
    return Call("GET", workspace_path(workspace_id, "/marketplace/installs"), returns_list=True)


# ---- webhooks --------------------------------------------------------


def list_webhooks(workspace_id: str) -> Call:
    return Call("GET", workspace_path(workspace_id, "/webhooks"), returns_list=True)


def create_webhook(
    workspace_id: str, *, url: str, events: list[str], description: str = ""
) -> Call:
    return Call(
        "POST",
        workspace_path(workspace_id, "/webhooks"),
        json_body={"url": url, "events": events, "description": description},
    )


def webhook_event_types(workspace_id: str) -> Call:
    return Call("GET", workspace_path(workspace_id, "/webhooks/events"), returns_list=True)


def list_deliveries(workspace_id: str, *, endpoint_id: str | None = None, limit: int = 50) -> Call:
    params: dict[str, Any] = {"limit": limit}
    params.update(_present(endpoint_id=endpoint_id))
    return Call(
        "GET",
        workspace_path(workspace_id, "/webhooks/deliveries"),
        params=params,
        returns_list=True,
    )


def rotate_webhook_secret(workspace_id: str, endpoint_id: str) -> Call:
    return Call("POST", workspace_path(workspace_id, f"/webhooks/{endpoint_id}/rotate-secret"))


def delete_webhook(workspace_id: str, endpoint_id: str) -> Call:
    return Call("DELETE", workspace_path(workspace_id, f"/webhooks/{endpoint_id}"))
