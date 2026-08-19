from __future__ import annotations

from pydantic import BaseModel


class CollabTicketResponse(BaseModel):
    ticket: str
    expires_in_seconds: int
