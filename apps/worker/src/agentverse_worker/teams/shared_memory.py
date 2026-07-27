"""Team shared memory, exposed to agents as SDK function tools.

Shared memory is how a team accumulates state that is not conversation:
the plan, findings so far, an intermediate artifact one member produced
and another needs. ADR-0009 makes two calls that this module implements
literally.

**It is relational, and shares nothing with the vector store.** Phase 5's
`kb_chunks` holds unstructured text retrieved by similarity; this holds
structured values written and read by key. The roadmap names merging
them as the phase's highest-risk mistake, because a single shared table
with a discriminator column is one forgotten `WHERE` away from letting
"what an agent remembers" contaminate "what a document says" — in both
directions, with no error raised.

**Agents reach it through tools, not through prompt stuffing.** Handing
every member the whole memory dictionary in its system prompt would
scale linearly with team size, bury the writes inside generated text,
and make "who wrote this" unanswerable. As `remember`/`recall` tool
calls, every access is an auditable row in the trace, and each member
pulls only the keys it asks for.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Text, case, select
from sqlalchemy import cast as sa_cast
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents import FunctionTool, Tool, function_tool
from agentverse_worker.teams.tables import shared_memory_table

logger = logging.getLogger(__name__)

#: Keys are namespace, not payload. A long key is either a mistake or an
#: attempt to smuggle content past the value cap.
MAX_KEY_CHARS = 200
#: Values are model-generated, which makes them untrusted input with an
#: unbounded natural size (CLAUDE.md §7). Capped on the serialized JSON
#: so nesting cannot evade it.
MAX_VALUE_BYTES = 64_000
#: What one `list_keys` call returns. A member that needs more than this
#: is not using memory as a key-value store.
MAX_LISTED_KEYS = 100

#: Scope precedence when the same key exists at several scopes: the
#: narrowest write wins, so an agent's own note shadows the team's.
_SCOPE_PRECEDENCE = {"agent": 0, "session": 1, "team": 2}


class SharedMemoryError(ValueError):
    """Raised for a rejected write. Surfaced to the agent as a tool
    result string rather than propagated — a bad `remember` call is the
    model's mistake to correct on the next turn, not a reason to fail the
    whole team session.
    """


class SharedMemoryStore:
    """Workspace- and team-scoped access to `shared_memory`.

    Every instance is bound to one workspace, team, and session at
    construction, and no method takes a workspace or team argument.
    That is deliberate: it makes cross-tenant access unexpressible here
    rather than merely checked (Rule 11), so no future caller can pass
    the wrong one.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        workspace_id: str,
        team_id: str,
        team_session_id: str,
        sharing_enabled: bool = True,
    ) -> None:
        self._factory = session_factory
        self._workspace_id = workspace_id
        self._team_id = team_id
        self._session_id = team_session_id
        self._sharing_enabled = sharing_enabled

    def _resolve_scope(self, requested: str, agent_id: str | None) -> str:
        """Narrows a requested scope to what the team's configuration
        permits.

        When `shared_memory_enabled` is false, every write collapses to
        `agent` scope. The tool is still offered rather than withdrawn so
        an agent's own scratch memory keeps working, and so a team that
        turns sharing off does not invalidate agent configurations that
        reference the tool.
        """
        scope = requested.strip().lower()
        if scope not in _SCOPE_PRECEDENCE:
            raise SharedMemoryError(
                f"unknown scope {requested!r}; expected one of team, session, agent"
            )
        if not self._sharing_enabled:
            return "agent"
        if scope == "agent" and agent_id is None:
            # The orchestrator branch has no agent identity to scope to.
            return "session"
        return scope

    async def remember(
        self,
        *,
        agent_id: str | None,
        key: str,
        value: dict[str, Any],
        scope: str = "session",
    ) -> str:
        """Upserts one entry. Returns the scope actually written, which
        may be narrower than requested (see `_resolve_scope`) — the
        caller reports it back to the agent so the model is never told a
        value is team-visible when it is not.
        """
        clean_key = key.strip()
        if not clean_key:
            raise SharedMemoryError("key must not be empty")
        if len(clean_key) > MAX_KEY_CHARS:
            raise SharedMemoryError(f"key exceeds {MAX_KEY_CHARS} characters")
        encoded = json.dumps(value, default=str)
        if len(encoded.encode("utf-8")) > MAX_VALUE_BYTES:
            raise SharedMemoryError(
                f"value exceeds {MAX_VALUE_BYTES} bytes; store a pointer to the "
                "artifact rather than the artifact itself"
            )

        effective = self._resolve_scope(scope, agent_id)
        row_session_id = None if effective == "team" else self._session_id
        row_agent_id = agent_id if effective == "agent" else None
        now = datetime.now(UTC)

        statement = (
            pg_insert(shared_memory_table)
            .values(
                id=str(uuid.uuid4()),
                workspace_id=self._workspace_id,
                team_id=self._team_id,
                session_id=row_session_id,
                agent_id=row_agent_id,
                scope=effective,
                key=clean_key,
                value=value,
                created_at=now,
                updated_at=now,
            )
            # The constraint is UNIQUE NULLS NOT DISTINCT, so this
            # matches team-scoped rows (null session/agent) too — with
            # Postgres's default NULL handling it would not, and every
            # team-scoped write would append instead of update.
            .on_conflict_do_update(
                constraint="uq_shared_memory_scope_key",
                set_={"value": value, "scope": effective, "updated_at": now},
            )
        )
        async with self._factory() as db:
            await db.execute(statement)
            await db.commit()
        return effective

    def _readable(self, agent_id: str | None) -> Any:
        """What this agent is allowed to see.

        Three disjoint cases, ORed: team-scoped entries for this team,
        session-scoped entries for this session, and this agent's own
        entries. An agent never sees another agent's `agent`-scoped
        writes — that is what makes the scope meaningful rather than
        decorative.
        """
        table = shared_memory_table
        base = (table.c.workspace_id == self._workspace_id) & (table.c.team_id == self._team_id)
        team_scoped = table.c.scope == "team"
        session_scoped = (table.c.scope == "session") & (table.c.session_id == self._session_id)
        own = (
            (table.c.scope == "agent")
            & (table.c.session_id == self._session_id)
            & (table.c.agent_id == agent_id)
            if agent_id is not None
            else (table.c.scope == "agent") & table.c.agent_id.is_(None)
        )
        if not self._sharing_enabled:
            # Sharing off: an agent reads only what it wrote itself.
            return base & own
        return base & (team_scoped | session_scoped | own)

    def _precedence_order(self) -> Any:
        """Orders matches narrowest-scope-first.

        `scope` is cast to text before the comparison: `case(value=...)`
        binds its WHEN labels as varchar, and Postgres has no
        `memory_scope = varchar` operator, so without the cast this is a
        `ProgrammingError` at query time rather than a wrong result.
        """
        return case(
            _SCOPE_PRECEDENCE,
            value=sa_cast(shared_memory_table.c.scope, Text),
            else_=len(_SCOPE_PRECEDENCE),
        )

    async def recall(self, *, agent_id: str | None, key: str) -> dict[str, Any] | None:
        """Reads one key at the narrowest scope visible to this agent."""
        table = shared_memory_table
        async with self._factory() as db:
            result = await db.execute(
                select(table.c.value)
                .where(self._readable(agent_id) & (table.c.key == key.strip()))
                .order_by(self._precedence_order())
                .limit(1)
            )
            value = result.scalar_one_or_none()
        if value is None:
            return None
        return dict(value)

    async def list_keys(self, *, agent_id: str | None) -> list[str]:
        """Keys this agent can read, so a member can discover what the
        team has recorded without guessing key names — the alternative is
        an agent that calls `recall` speculatively and burns turns on
        misses.
        """
        table = shared_memory_table
        async with self._factory() as db:
            result = await db.execute(
                select(table.c.key)
                .where(self._readable(agent_id))
                .distinct()
                .order_by(table.c.key)
                .limit(MAX_LISTED_KEYS)
            )
            return list(result.scalars().all())


def build_shared_memory_tools(store: SharedMemoryStore, *, agent_id: str | None) -> list[Tool]:
    """Binds a store and an agent identity into SDK function tools.

    A closure rather than a tool that takes `agent_id` as a parameter:
    tool arguments come from the model and are untrusted (CLAUDE.md §4),
    so letting the model name the agent whose memory it is writing would
    hand it the ability to write as another member. Bound here, the
    identity is not addressable from the prompt at all.

    Errors are returned as strings rather than raised. A malformed
    `remember` call is a turn the model can correct; raising would abort
    the whole team session over one bad argument.
    """

    @function_tool
    async def remember(key: str, value: str, scope: str = "session") -> str:
        """Saves a value to the team's shared memory under a key.

        Args:
            key: Short identifier to store under, e.g. "research_findings".
            value: The content to store. JSON is kept structured; anything
                else is stored as text.
            scope: Who can read it — "team" (all members, all sessions),
                "session" (all members, this run), or "agent" (only you).
        """
        try:
            parsed = json.loads(value)
            payload: dict[str, Any] = parsed if isinstance(parsed, dict) else {"value": parsed}
        except (json.JSONDecodeError, TypeError):
            payload = {"value": value}
        try:
            effective = await store.remember(agent_id=agent_id, key=key, value=payload, scope=scope)
        except SharedMemoryError as exc:
            return f"error: {exc}"
        if effective != scope:
            return (
                f"Saved {key!r} at {effective} scope. "
                f"({scope!r} was narrowed — sharing is disabled for this team.)"
            )
        return f"Saved {key!r} at {effective} scope."

    @function_tool
    async def recall(key: str) -> str:
        """Reads a value another team member (or you) saved earlier.

        Args:
            key: The identifier the value was saved under.
        """
        value = await store.recall(agent_id=agent_id, key=key)
        if value is None:
            available = await store.list_keys(agent_id=agent_id)
            if not available:
                return f"No value stored for {key!r}; shared memory is empty."
            return f"No value stored for {key!r}. Available keys: {', '.join(available)}"
        return json.dumps(value, default=str)

    @function_tool
    async def list_memory_keys() -> str:
        """Lists every shared-memory key you are allowed to read."""
        keys = await store.list_keys(agent_id=agent_id)
        if not keys:
            return "Shared memory is empty."
        return ", ".join(keys)

    tools: list[FunctionTool] = [remember, recall, list_memory_keys]
    # Returned as `list[Tool]` (the SDK's broader union) because
    # `Agent.tools` expects that and list invariance means a
    # `list[FunctionTool]` does not satisfy it.
    return list(tools)
