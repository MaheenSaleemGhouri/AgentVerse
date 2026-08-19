"""Short-lived, single-use WebSocket auth tickets for workflow-canvas
collaboration (docs/adr/0016).

Native `WebSocket`, like `EventSource`, cannot set custom headers, and
the browser never holds the raw Bearer JWT (SSE solves this with a
same-origin Next.js proxy that resolves the session cookie to a token —
a trick that doesn't extend to a long-lived bidirectional socket). This
mints an opaque token via an authenticated REST call instead; the
browser then connects directly to the WS endpoint with `?ticket=...`,
and the handshake validates + burns it before `accept()`.

Redis-backed (not in-process): the mint and the WS handshake can land on
different API instances behind a load balancer.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass

from redis.asyncio import Redis

_TICKET_TTL_SECONDS = 30
_KEY_PREFIX = "collab-ticket:"


@dataclass(frozen=True, slots=True)
class CollabTicketPayload:
    workspace_id: str
    workflow_id: str
    user_id: str
    role: str


async def mint_ticket(
    *, workspace_id: str, workflow_id: str, user_id: str, role: str, redis: Redis
) -> tuple[str, int]:
    ticket = secrets.token_urlsafe(32)
    payload = CollabTicketPayload(
        workspace_id=workspace_id, workflow_id=workflow_id, user_id=user_id, role=role
    )
    await redis.setex(
        f"{_KEY_PREFIX}{ticket}",
        _TICKET_TTL_SECONDS,
        json.dumps(
            {
                "workspace_id": payload.workspace_id,
                "workflow_id": payload.workflow_id,
                "user_id": payload.user_id,
                "role": payload.role,
            }
        ),
    )
    return ticket, _TICKET_TTL_SECONDS


async def resolve_and_burn_ticket(*, ticket: str, redis: Redis) -> CollabTicketPayload | None:
    """Single-use: `GETDEL` atomically reads and removes the key, so a
    replayed ticket (or two connections racing the same one) can only
    ever succeed once.
    """
    raw = await redis.getdel(f"{_KEY_PREFIX}{ticket}")
    if raw is None:
        return None
    data = json.loads(raw)
    return CollabTicketPayload(
        workspace_id=data["workspace_id"],
        workflow_id=data["workflow_id"],
        user_id=data["user_id"],
        role=data["role"],
    )
