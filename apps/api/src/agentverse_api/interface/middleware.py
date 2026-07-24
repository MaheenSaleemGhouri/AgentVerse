"""Request-scoped correlation ID middleware.

Binds a `request_id` (client-supplied via `X-Request-Id`, generated
otherwise) into `infrastructure.logging.request_id_var` for the
duration of the request, and echoes it back on the response so a
client can correlate its own logs with ours.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import uuid4

from starlette.requests import Request
from starlette.responses import Response

from agentverse_api.infrastructure.logging import request_id_var

REQUEST_ID_HEADER = "X-Request-Id"


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get(REQUEST_ID_HEADER, str(uuid4()))
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response
