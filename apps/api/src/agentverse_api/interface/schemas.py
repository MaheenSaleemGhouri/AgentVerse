"""Response schemas for the interface layer.

Every response is a Pydantic v2 model — no raw `dict`/`Any` I/O
(CLAUDE.md §7).
"""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
