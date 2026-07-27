from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateAgentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    model: str = Field(min_length=1, max_length=64)
    # Reaches an LLM prompt — capped per CLAUDE.md §7 to bound
    # prompt-injection blast radius and cost, same as any other
    # free-text field that ends up in a completion request.
    system_instructions: str = Field(min_length=1, max_length=8000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, ge=1, le=32000)
    tools: list[str] = Field(default_factory=list, max_length=20)
    # Capped like `tools`: each attached KB is another retrieval arm
    # pair per run, so an unbounded list is a latency and cost vector.
    knowledge_base_ids: list[str] = Field(default_factory=list, max_length=10)


class UpdateAgentVersionRequest(BaseModel):
    model: str = Field(min_length=1, max_length=64)
    # Reaches an LLM prompt — capped per CLAUDE.md §7 to bound
    # prompt-injection blast radius and cost, same as any other
    # free-text field that ends up in a completion request.
    system_instructions: str = Field(min_length=1, max_length=8000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, ge=1, le=32000)
    tools: list[str] = Field(default_factory=list, max_length=20)
    # Capped like `tools`: each attached KB is another retrieval arm
    # pair per run, so an unbounded list is a latency and cost vector.
    knowledge_base_ids: list[str] = Field(default_factory=list, max_length=10)


class AgentVersionResponse(BaseModel):
    id: str
    version_number: int
    model: str
    system_instructions: str
    temperature: float | None
    max_output_tokens: int | None
    tools: list[str]
    knowledge_base_ids: list[str]
    created_at: datetime


class AgentResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str | None
    status: str
    published_version_id: str | None
    created_at: datetime
    updated_at: datetime


class CreateAgentResponse(BaseModel):
    agent: AgentResponse
    version: AgentVersionResponse


class RunAgentRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


class RunResponse(BaseModel):
    id: str
    agent_id: str
    status: str
    idempotency_key: str | None
    cost_micro_usd: int | None
    error_message: str | None
    created_at: datetime
