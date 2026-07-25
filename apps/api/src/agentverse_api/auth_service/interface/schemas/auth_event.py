from __future__ import annotations

from pydantic import BaseModel

from agentverse_api.auth_service.application.auth_event_service import AuthEventType


class RecordAuthEventRequest(BaseModel):
    event_type: AuthEventType
    user_id: str
