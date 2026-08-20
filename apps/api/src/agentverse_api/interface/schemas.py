"""Response schemas for the interface layer.

Every response is a Pydantic v2 model — no raw `dict`/`Any` I/O
(CLAUDE.md §7).
"""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    #: docs/adr/0019 — which regional deployment answered this request.
    #: `"primary"` in every environment today (only one region is
    #: deployed); present now so a second region's rollout is additive
    #: to the contract, not a breaking change to it.
    region: str
