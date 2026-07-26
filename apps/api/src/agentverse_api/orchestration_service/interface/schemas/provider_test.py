"""Request schema for the internal provider-test route. Pydantic v2,
field-constrained — no raw `dict`/`Any` I/O (CLAUDE.md §7 Validation).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProviderTestRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    model: str | None = Field(default=None, max_length=64)
