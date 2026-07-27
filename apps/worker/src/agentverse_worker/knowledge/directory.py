"""Resolves the embedding identity of an agent's attached knowledge bases.

Separate from `knowledge/repository.py` on purpose: that repository is
the ingestion job's read/write surface, and the run path must not be able
to reach a write through the object it was handed (interface segregation,
CLAUDE.md §3). This is one scoped read and nothing else.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_worker.agents.grounding import KnowledgeBaseIdentity
from agentverse_worker.knowledge.tables import knowledge_bases_table


class WorkerKnowledgeBaseDirectory:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_embedding_identities(
        self, *, workspace_id: str, knowledge_base_ids: list[str]
    ) -> list[KnowledgeBaseIdentity]:
        if not knowledge_base_ids:
            return []
        result = await self._session.execute(
            select(
                knowledge_bases_table.c.id,
                knowledge_bases_table.c.embedding_model,
                knowledge_bases_table.c.embedding_model_version,
            ).where(
                # `workspace_id` from the run record, which came from the
                # authenticated caller at submit time — a KB id in an
                # agent config is not proof of ownership (Rule 11).
                knowledge_bases_table.c.workspace_id == workspace_id,
                knowledge_bases_table.c.id.in_(knowledge_base_ids),
                # A KB deleted after the agent version was published must
                # stop grounding runs, not keep serving stale chunks.
                knowledge_bases_table.c.deleted_at.is_(None),
            )
        )
        return [KnowledgeBaseIdentity(*row) for row in result.all()]
