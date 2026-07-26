from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class JobTestRequest(BaseModel):
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary payload the echo job reports back."
    )
    force_fail: bool = Field(
        default=False, description="If true, the echo job always fails — exercises retry/DLQ."
    )
    max_attempts: int = Field(default=3, ge=1, le=10)


class JobTestResponse(BaseModel):
    job_id: str
    stream_id: str
