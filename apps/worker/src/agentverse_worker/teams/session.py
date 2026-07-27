"""A Postgres-backed implementation of the Agents SDK's `Session`
protocol.

The SDK already owns conversation management — trimming, ordering,
replaying items into the next turn. What it does not own is *where* the
items live: its shipped implementations are in-memory and SQLite, and on
a multi-instance worker fleet both silently drop state the moment a
follow-up turn is picked up by a different instance. That is a wrong
answer that produces no error, which is why CLAUDE.md §4 names it
explicitly.

So this implements the protocol and nothing more. No trimming policy, no
summarisation, no custom replay logic — all of that is SDK behavior and
reimplementing it here would be exactly the duplication ADR-0009 rules
out.

Two design points worth stating because both are easy to get wrong:

**One DB transaction per protocol call, never one per Runner turn.** The
SDK calls `get_items`/`add_items` around each model call. Holding a
session open across that boundary would pin a pooled connection for the
duration of an LLM request (CLAUDE.md §7), so each method opens and
closes its own short transaction via the factory.

**One branch per member, not one per team session.** A parallel topology
runs several members concurrently on the same input; merging their turns
into a single history would hand each of them the others' partial
reasoning as if it were their own. Branches are keyed by
`(session_id, agent_id)`, and what crosses between them is a
`HandoffContract`, never raw items.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.items import TResponseInputItem
from agents.memory.session_settings import SessionSettings
from agentverse_worker.teams.tables import team_session_items_table


class PostgresTeamSession:
    """Structurally satisfies `agents.memory.session.Session`.

    Deliberately not a subclass of the SDK's `SessionABC`: that base is
    documented as internal, and the SDK tells third-party implementations
    to satisfy the `Session` protocol instead. Structural typing means an
    SDK change to the ABC cannot break this class silently.
    """

    #: Required by the protocol. Composite so two members of the same
    #: team session are distinct sessions to the SDK, which is the point.
    session_id: str
    session_settings: SessionSettings | None = None

    def __init__(
        self,
        *,
        team_session_id: str,
        workspace_id: str,
        session_factory: async_sessionmaker[AsyncSession],
        agent_id: str | None = None,
        session_settings: SessionSettings | None = None,
    ) -> None:
        self._team_session_id = team_session_id
        self._workspace_id = workspace_id
        self._agent_id = agent_id
        self._factory = session_factory
        self.session_id = f"{team_session_id}:{agent_id or 'orchestrator'}"
        self.session_settings = session_settings

    def _branch_filter(self) -> Any:
        """The `(session_id, agent_id)` predicate every query shares.

        `agent_id IS NULL` needs `.is_(None)` rather than `== None`, and
        getting that wrong would silently match zero rows — the
        orchestrator branch would appear empty rather than error.
        """
        table = team_session_items_table
        # Workspace scoping is redundant with session_id (a session
        # belongs to exactly one workspace) and included anyway: Rule 11
        # is that every query filters by workspace_id, and a redundant
        # predicate costs nothing next to a missing one.
        clause = (table.c.session_id == self._team_session_id) & (
            table.c.workspace_id == self._workspace_id
        )
        if self._agent_id is None:
            return clause & table.c.agent_id.is_(None)
        return clause & (table.c.agent_id == self._agent_id)

    async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        """Chronological history for this branch.

        With `limit`, the protocol asks for the *latest* N still in
        chronological order — hence selecting descending, then reversing,
        rather than taking the first N (which would return the oldest).
        """
        table = team_session_items_table
        query = select(table.c.item).where(self._branch_filter()).order_by(table.c.id.desc())
        if limit is not None:
            if limit <= 0:
                return []
            query = query.limit(limit)
        async with self._factory() as db:
            result = await db.execute(query)
            rows = list(result.scalars().all())
        rows.reverse()
        return [cast(TResponseInputItem, row) for row in rows]

    async def add_items(self, items: list[TResponseInputItem]) -> None:
        """Appends items in one multi-row insert.

        A row-by-row loop here would be both slower and non-atomic —
        a failure mid-loop would leave a half-written turn that the next
        `get_items` would replay as if it were complete.
        """
        if not items:
            return
        now = datetime.now(UTC)
        rows = [
            {
                "created_at": now,
                "session_id": self._team_session_id,
                "workspace_id": self._workspace_id,
                "agent_id": self._agent_id,
                "item": item,
            }
            for item in items
        ]
        async with self._factory() as db:
            await db.execute(team_session_items_table.insert(), rows)
            await db.commit()

    async def pop_item(self) -> TResponseInputItem | None:
        """Removes and returns the most recent item in this branch.

        The delete targets the row by `(id, created_at)` rather than by
        `MAX(id)` in a subquery: the table is partitioned by `created_at`,
        so naming the partition key lets Postgres prune to one partition
        instead of scanning every one to find the maximum.
        """
        table = team_session_items_table
        async with self._factory() as db:
            result = await db.execute(
                select(table.c.id, table.c.created_at, table.c.item)
                .where(self._branch_filter())
                .order_by(table.c.id.desc())
                .limit(1)
                .with_for_update()
            )
            row = result.mappings().one_or_none()
            if row is None:
                return None
            await db.execute(
                delete(table).where(
                    (table.c.id == row["id"]) & (table.c.created_at == row["created_at"])
                )
            )
            await db.commit()
        return cast(TResponseInputItem, row["item"])

    async def clear_session(self) -> None:
        """Deletes every item in this branch.

        Scoped to the branch, not the team session: clearing one member's
        history must not wipe the rest of the team's.
        """
        async with self._factory() as db:
            await db.execute(delete(team_session_items_table).where(self._branch_filter()))
            await db.commit()
