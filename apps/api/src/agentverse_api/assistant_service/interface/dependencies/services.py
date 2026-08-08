"""Composition root for the assistant."""

from __future__ import annotations

from functools import lru_cache

from agentverse_api.assistant_service.application.assistant_service import AssistantService
from agentverse_api.assistant_service.domain.ports import DocsIndex
from agentverse_api.assistant_service.infrastructure.docs_index import CorpusDocsIndex
from agentverse_api.assistant_service.infrastructure.unit_of_work import sql_unit_of_work
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_provider_adapter,
)


@lru_cache
def get_docs_index() -> DocsIndex:
    """Loaded once per process. The corpus is a committed artifact that
    cannot change without a redeploy, so re-reading it per request would
    buy nothing but file I/O on the hot path."""
    return CorpusDocsIndex()


def get_assistant_service() -> AssistantService:
    """Takes no session dependency on purpose — see `sql_unit_of_work`."""
    return AssistantService(
        unit_of_work=sql_unit_of_work,
        docs=get_docs_index(),
        adapter=get_provider_adapter(),
    )
