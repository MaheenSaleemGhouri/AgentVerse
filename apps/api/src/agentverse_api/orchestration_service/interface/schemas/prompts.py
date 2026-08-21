"""Request/response schemas for the prompt-versioning/eval-harness admin
surface (Phase 8). Every I/O boundary is a Pydantic v2 model — no raw
`dict`/`Any` (CLAUDE.md §7).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PromptTemplateResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime


class PromptVersionResponse(BaseModel):
    id: str
    prompt_template_id: str
    version_number: int
    system_instructions: str
    model: str
    temperature: float | None
    status: str
    created_at: datetime
    activated_at: datetime | None


class CreateDraftVersionRequest(BaseModel):
    system_instructions: str = Field(min_length=1, max_length=20_000)
    model: str = Field(min_length=1, max_length=64)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)


class ExampleResultResponse(BaseModel):
    golden_example_id: str
    passed: bool
    reason: str
    cost_micro_usd: int
    latency_ms: int


class EvalRunResponse(BaseModel):
    id: str
    prompt_version_id: str
    started_at: datetime
    completed_at: datetime | None
    passed: bool
    total_examples: int
    passed_examples: int
    total_cost_micro_usd: int
    total_latency_ms: int
    results: list[ExampleResultResponse]


class PromoteVersionResponse(BaseModel):
    version: PromptVersionResponse
    archived_version: PromptVersionResponse | None
