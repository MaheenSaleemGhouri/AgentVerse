"""Request/response models for the assistant routes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from agentverse_api.assistant_service.domain.entities import MAX_QUESTION_LENGTH


class AskRequest(BaseModel):
    """`min_length=1` after stripping, so a stray Enter cannot spend a
    provider call on an empty prompt."""

    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)


class SessionResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    last_message_at: datetime


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
