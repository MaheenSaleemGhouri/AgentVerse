"""Usage metering against real Postgres.

What only the database can prove: that the table is actually partitioned,
that a row lands in the partition its timestamp says it should, that the
unique index survives partitioning (Postgres requires the partition key
in it, which is easy to get subtly wrong), and that the DEFAULT
partition catches a row no monthly partition covers rather than
rejecting it.

That last one matters most. A billing record that fails to insert is
revenue nobody can reconstruct.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.billing_service.domain.plan import MeteredDimension
from agentverse_api.billing_service.domain.usage import UsageEvent, UsageSource
from agentverse_api.billing_service.infrastructure.repositories import SqlUsageRepository

pytestmark = pytest.mark.integration

_NOW = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)


def _event(
    workspace_id: str,
    *,
    dimension: MeteredDimension = MeteredDimension.AGENT_RUNS,
    quantity: int = 1,
    at: datetime | None = None,
    key: str | None = None,
    cost: int | None = None,
) -> UsageEvent:
    source_id = key or f"run-{uuid.uuid4().hex[:10]}"
    return UsageEvent(
        workspace_id=workspace_id,
        dimension=dimension,
        quantity=quantity,
        occurred_at=at or _NOW,
        source=UsageSource.AGENT_RUN,
        source_id=source_id,
        idempotency_key=f"run:{source_id}:{dimension.value}",
        cost_micro_usd=cost,
    )


class TestPartitioning:
    async def test_the_table_is_actually_partitioned_by_range(
        self, db_session: AsyncSession
    ) -> None:
        # Asserted against the deployed schema, not the migration file: a
        # billing table is the worst candidate for a partitioning
        # migration later, so this must be true from the start.
        result = await db_session.execute(
            text(
                "SELECT partstrat FROM pg_partitioned_table "
                "WHERE partrelid = 'billing_usage_events'::regclass"
            )
        )
        # `partstrat` is a `char` column, which asyncpg hands back as
        # bytes rather than str. `r` = RANGE.
        assert result.scalar_one() == b"r"

    async def test_a_default_partition_exists(self, db_session: AsyncSession) -> None:
        # Without it, an insert for an un-provisioned month is rejected
        # outright — and a billing record that fails to insert is revenue
        # nobody can reconstruct.
        result = await db_session.execute(
            text(
                "SELECT count(*) FROM pg_class c "
                "JOIN pg_inherits i ON i.inhrelid = c.oid "
                "WHERE i.inhparent = 'billing_usage_events'::regclass "
                "AND c.relname = 'billing_usage_events_default'"
            )
        )
        assert result.scalar_one() == 1

    async def test_a_row_lands_in_the_partition_its_timestamp_implies(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = str(uuid.uuid4())
        await SqlUsageRepository(db_session).record([_event(workspace_id)])
        await db_session.flush()
        result = await db_session.execute(
            text(
                "SELECT tableoid::regclass::text FROM billing_usage_events WHERE workspace_id = :ws"
            ),
            {"ws": workspace_id},
        )
        landed = result.scalar_one()
        assert landed == f"billing_usage_events_{_NOW.year:04d}_{_NOW.month:02d}"
        await db_session.rollback()

    async def test_a_far_future_row_falls_to_default_rather_than_failing(
        self, db_session: AsyncSession
    ) -> None:
        # Beyond the pre-created window. The insert must succeed.
        workspace_id = str(uuid.uuid4())
        far_future = _NOW + timedelta(days=365 * 4)
        written = await SqlUsageRepository(db_session).record([_event(workspace_id, at=far_future)])
        await db_session.flush()
        assert written == 1
        result = await db_session.execute(
            text(
                "SELECT tableoid::regclass::text FROM billing_usage_events WHERE workspace_id = :ws"
            ),
            {"ws": workspace_id},
        )
        assert result.scalar_one() == "billing_usage_events_default"
        await db_session.rollback()


class TestIdempotency:
    async def test_recording_the_same_key_twice_writes_once(self, db_session: AsyncSession) -> None:
        workspace_id = str(uuid.uuid4())
        repo = SqlUsageRepository(db_session)
        event = _event(workspace_id, key="stable")
        assert await repo.record([event]) == 1
        assert await repo.record([event]) == 0
        usage = await repo.usage_for_period(
            workspace_id=workspace_id,
            period_start=_NOW - timedelta(days=1),
            period_end=_NOW + timedelta(days=1),
        )
        assert usage.quantity(MeteredDimension.AGENT_RUNS) == 1
        await db_session.rollback()

    async def test_the_unique_index_survives_partitioning(self, db_session: AsyncSession) -> None:
        # Postgres requires the partition key in every unique index on a
        # partitioned table; the repository's ON CONFLICT hides a
        # mistake here, so the constraint is asserted directly.
        workspace_id = str(uuid.uuid4())
        insert = text(
            "INSERT INTO billing_usage_events "
            "(id, occurred_at, workspace_id, dimension, source, quantity, idempotency_key) "
            "VALUES (gen_random_uuid(), :at, :ws, 'agent_runs', 'agent_run', 1, 'dup')"
        )
        params = {"at": _NOW, "ws": workspace_id}
        await db_session.execute(insert, params)
        with pytest.raises(IntegrityError):
            await db_session.execute(insert, params)
        await db_session.rollback()


class TestAggregation:
    async def test_accumulating_dimensions_sum_across_events(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = str(uuid.uuid4())
        repo = SqlUsageRepository(db_session)
        await repo.record([_event(workspace_id) for _ in range(5)])
        usage = await repo.usage_for_period(
            workspace_id=workspace_id,
            period_start=_NOW - timedelta(days=1),
            period_end=_NOW + timedelta(days=1),
        )
        assert usage.quantity(MeteredDimension.AGENT_RUNS) == 5
        await db_session.rollback()

    async def test_storage_takes_the_maximum_not_the_sum(self, db_session: AsyncSession) -> None:
        # Summing snapshots would multiply the storage bill by however
        # often the snapshot job ran.
        workspace_id = str(uuid.uuid4())
        repo = SqlUsageRepository(db_session)
        await repo.record(
            [
                _event(
                    workspace_id,
                    dimension=MeteredDimension.VECTOR_STORAGE_MB,
                    quantity=size,
                )
                for size in (4000, 5000, 4500)
            ]
        )
        usage = await repo.usage_for_period(
            workspace_id=workspace_id,
            period_start=_NOW - timedelta(days=1),
            period_end=_NOW + timedelta(days=1),
        )
        assert usage.quantity(MeteredDimension.VECTOR_STORAGE_MB) == 5000
        await db_session.rollback()

    async def test_another_workspaces_usage_is_never_counted(
        self, db_session: AsyncSession
    ) -> None:
        # Rule 11 at the query layer: the aggregate filters on
        # `workspace_id`, so one tenant's runs can never reach another's
        # invoice.
        mine = str(uuid.uuid4())
        theirs = str(uuid.uuid4())
        repo = SqlUsageRepository(db_session)
        await repo.record([_event(mine), _event(theirs), _event(theirs)])
        usage = await repo.usage_for_period(
            workspace_id=mine,
            period_start=_NOW - timedelta(days=1),
            period_end=_NOW + timedelta(days=1),
        )
        assert usage.quantity(MeteredDimension.AGENT_RUNS) == 1
        await db_session.rollback()

    async def test_events_outside_the_window_are_excluded(self, db_session: AsyncSession) -> None:
        workspace_id = str(uuid.uuid4())
        repo = SqlUsageRepository(db_session)
        await repo.record(
            [_event(workspace_id), _event(workspace_id, at=_NOW - timedelta(days=40))]
        )
        usage = await repo.usage_for_period(
            workspace_id=workspace_id,
            period_start=_NOW - timedelta(days=1),
            period_end=_NOW + timedelta(days=1),
        )
        assert usage.quantity(MeteredDimension.AGENT_RUNS) == 1
        await db_session.rollback()

    async def test_provider_cost_is_summed_in_micro_usd(self, db_session: AsyncSession) -> None:
        workspace_id = str(uuid.uuid4())
        repo = SqlUsageRepository(db_session)
        await repo.record(
            [
                _event(workspace_id, dimension=MeteredDimension.TOKENS, quantity=100, cost=450),
                _event(workspace_id, dimension=MeteredDimension.TOKENS, quantity=200, cost=910),
            ]
        )
        usage = await repo.usage_for_period(
            workspace_id=workspace_id,
            period_start=_NOW - timedelta(days=1),
            period_end=_NOW + timedelta(days=1),
        )
        assert usage.cost_micro_usd(MeteredDimension.TOKENS) == 1360
        await db_session.rollback()


class TestRollups:
    async def test_writing_rollups_twice_updates_rather_than_duplicating(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = str(uuid.uuid4())
        repo = SqlUsageRepository(db_session)
        start = _NOW - timedelta(days=1)
        end = _NOW + timedelta(days=1)
        await repo.record([_event(workspace_id) for _ in range(3)])
        usage = await repo.usage_for_period(
            workspace_id=workspace_id, period_start=start, period_end=end
        )
        await repo.write_rollups(
            workspace_id=workspace_id,
            period_start=start,
            period_end=end,
            usage=usage,
            finalize=False,
        )
        await repo.write_rollups(
            workspace_id=workspace_id,
            period_start=start,
            period_end=end,
            usage=usage,
            finalize=True,
        )
        result = await db_session.execute(
            text("SELECT count(*) FROM billing_usage_rollups WHERE workspace_id = :ws"),
            {"ws": workspace_id},
        )
        assert result.scalar_one() == 1
        await db_session.rollback()

    async def test_unfinalized_rollups_are_not_returned_for_invoicing(
        self, db_session: AsyncSession
    ) -> None:
        # Invoicing a period still in progress would bill a number that
        # then moves.
        workspace_id = str(uuid.uuid4())
        repo = SqlUsageRepository(db_session)
        start = _NOW - timedelta(days=1)
        end = _NOW + timedelta(days=1)
        await repo.record([_event(workspace_id)])
        usage = await repo.usage_for_period(
            workspace_id=workspace_id, period_start=start, period_end=end
        )
        await repo.write_rollups(
            workspace_id=workspace_id,
            period_start=start,
            period_end=end,
            usage=usage,
            finalize=False,
        )
        assert await repo.finalized_rollups(workspace_id=workspace_id, period_start=start) is None
        await db_session.rollback()

    async def test_finalized_rollups_are_returned(self, db_session: AsyncSession) -> None:
        workspace_id = str(uuid.uuid4())
        repo = SqlUsageRepository(db_session)
        start = _NOW - timedelta(days=1)
        end = _NOW + timedelta(days=1)
        await repo.record([_event(workspace_id) for _ in range(7)])
        usage = await repo.usage_for_period(
            workspace_id=workspace_id, period_start=start, period_end=end
        )
        await repo.write_rollups(
            workspace_id=workspace_id,
            period_start=start,
            period_end=end,
            usage=usage,
            finalize=True,
        )
        stored = await repo.finalized_rollups(workspace_id=workspace_id, period_start=start)
        assert stored is not None
        assert stored.quantity(MeteredDimension.AGENT_RUNS) == 7
        await db_session.rollback()


class TestConstraints:
    async def test_a_negative_quantity_is_rejected_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO billing_usage_events "
                    "(id, occurred_at, workspace_id, dimension, source, quantity, "
                    " idempotency_key) "
                    "VALUES (gen_random_uuid(), :at, :ws, 'agent_runs', 'agent_run', -1, :k)"
                ),
                {"at": _NOW, "ws": str(uuid.uuid4()), "k": f"neg-{uuid.uuid4().hex[:8]}"},
            )
        await db_session.rollback()

    async def test_an_inverted_rollup_period_is_rejected(self, db_session: AsyncSession) -> None:
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO billing_usage_rollups "
                    "(id, workspace_id, period_start, period_end, dimension) "
                    "VALUES (gen_random_uuid(), :ws, :start, :end, 'agent_runs')"
                ),
                {
                    "ws": str(uuid.uuid4()),
                    "start": _NOW,
                    "end": _NOW - timedelta(days=1),
                },
            )
        await db_session.rollback()
