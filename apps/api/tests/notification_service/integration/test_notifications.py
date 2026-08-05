"""Notifications against real Postgres.

The two guarantees worth proving here are both database ones, and both
fail in the same visible way if they break: the customer gets told the
same thing three times, and learns to ignore billing mail.

- `notifications.dedupe_key` is unique, so a sweep that runs twice and a
  redelivered webhook produce one notification.
- `(notification_id, channel)` is unique on deliveries, so a retried
  dispatch sends one email.

Neither can be proven against a fake, because both failures happen when
two writes are concurrent — which is exactly what an application-level
"have I done this?" check cannot serialize.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.notification_service.application.billing_notifier import BillingNotifier
from agentverse_api.notification_service.application.notification_service import (
    NotificationService,
)
from agentverse_api.notification_service.domain import templates
from agentverse_api.notification_service.domain.notification import (
    NotificationKind,
    Severity,
)
from agentverse_api.notification_service.infrastructure.email.logging_sender import (
    LoggingEmailSender,
)
from agentverse_api.notification_service.infrastructure.repositories import (
    SqlDeliveryRepository,
    SqlNotificationRepository,
)

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 8, 24, tzinfo=UTC)


class _RecordingSender:
    """Counts sends so "was one email sent, or three?" is assertable."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail_with: Exception | None = None

    async def send(self, *, to: str, subject: str, body: str) -> str | None:
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append((to, subject))
        return f"msg_{len(self.sent)}"


async def _workspace(session: AsyncSession) -> str:
    workspace_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO workspaces (id, name, slug, created_at) "
            "VALUES (:id, 'Notify Test', :slug, now())"
        ),
        {"id": workspace_id, "slug": f"ws-{workspace_id[:8]}"},
    )
    await session.flush()
    return workspace_id


def _service(session: AsyncSession, sender: _RecordingSender | None = None) -> NotificationService:
    return NotificationService(
        notifications=SqlNotificationRepository(session),
        deliveries=SqlDeliveryRepository(session),
        email=sender or LoggingEmailSender(),
        app_base_url="https://app.agentverse.test",
    )


def _message() -> templates.RenderedMessage:
    return templates.payment_failed(workspace_id="ws-1", amount_cents=2900, deadline=_NOW)


class TestDeduplication:
    async def test_the_same_dedupe_key_creates_one_notification(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        key = f"payment_failed:{workspace_id}"
        first = await service.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.PAYMENT_FAILED,
            message=_message(),
            dedupe_key=key,
        )
        second = await service.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.PAYMENT_FAILED,
            message=_message(),
            dedupe_key=key,
        )
        assert first is not None
        # `None`, not an exception: a duplicate is the normal outcome of
        # a retry, and a caller should not catch for that.
        assert second is None
        assert len(await service.list_for(workspace_id=workspace_id)) == 1
        await db_session.rollback()

    async def test_the_uniqueness_is_enforced_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        # The repository's ON CONFLICT hides this, so the constraint is
        # asserted directly — a refactor to select-then-insert would
        # pass every other test in this file.
        workspace_id = await _workspace(db_session)
        insert = text(
            "INSERT INTO notifications "
            "(id, workspace_id, kind, severity, title, body, dedupe_key) "
            "VALUES (gen_random_uuid(), :ws, 'payment_failed', 'critical', 't', 'b', 'dup')"
        )
        await db_session.execute(insert, {"ws": workspace_id})
        with pytest.raises(IntegrityError):
            await db_session.execute(insert, {"ws": workspace_id})
        await db_session.rollback()

    async def test_different_keys_create_different_notifications(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        for day in (0, 3, 7):
            await service.raise_(
                workspace_id=workspace_id,
                kind=NotificationKind.DUNNING_REMINDER,
                message=_message(),
                dedupe_key=f"dunning:{workspace_id}:{day}",
            )
        assert len(await service.list_for(workspace_id=workspace_id)) == 3
        await db_session.rollback()


class TestEmailDelivery:
    async def test_a_blocking_kind_is_emailed(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        sender = _RecordingSender()
        service = _service(db_session, sender)
        await service.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.PAYMENT_FAILED,
            message=_message(),
            dedupe_key=f"k:{workspace_id}",
            recipient="finance@example.test",
        )
        assert len(sender.sent) == 1
        assert sender.sent[0][0] == "finance@example.test"
        await db_session.rollback()

    async def test_a_receipt_is_recorded_but_not_emailed(self, db_session: AsyncSession) -> None:
        # A customer served well does not need an email every month
        # telling them nothing changed.
        workspace_id = await _workspace(db_session)
        sender = _RecordingSender()
        service = _service(db_session, sender)
        notification = await service.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.PAYMENT_SUCCEEDED,
            message=templates.payment_succeeded(
                workspace_id=workspace_id, amount_cents=2900, plan_name="Pro"
            ),
            dedupe_key=f"k:{workspace_id}",
            recipient="finance@example.test",
        )
        assert notification is not None
        assert sender.sent == []
        await db_session.rollback()

    async def test_no_recipient_records_the_notification_and_skips_the_email(
        self, db_session: AsyncSession
    ) -> None:
        # Mailing a fallback would send billing correspondence to
        # whoever happened to sign up rather than to whoever handles
        # billing.
        workspace_id = await _workspace(db_session)
        sender = _RecordingSender()
        service = _service(db_session, sender)
        notification = await service.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.PAYMENT_FAILED,
            message=_message(),
            dedupe_key=f"k:{workspace_id}",
            recipient=None,
        )
        assert notification is not None
        assert sender.sent == []
        await db_session.rollback()

    async def test_the_link_placeholder_is_substituted_with_an_absolute_url(
        self, db_session: AsyncSession
    ) -> None:
        # A relative path in an email is not clickable.
        workspace_id = await _workspace(db_session)
        sender = _RecordingSender()

        sent_bodies: list[str] = []

        async def capture(*, to: str, subject: str, body: str) -> str | None:
            sent_bodies.append(body)
            return "msg_1"

        sender.send = capture  # type: ignore[method-assign]
        service = _service(db_session, sender)
        await service.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.PAYMENT_FAILED,
            message=_message(),
            dedupe_key=f"k:{workspace_id}",
            recipient="finance@example.test",
        )
        assert "{link}" not in sent_bodies[0]
        assert "https://app.agentverse.test/dashboard/" in sent_bodies[0]
        await db_session.rollback()

    async def test_a_failed_send_does_not_lose_the_notification(
        self, db_session: AsyncSession
    ) -> None:
        # The whole point of separating deliveries from notifications:
        # the customer was still told in-app, and the failure is
        # recorded rather than raised into a billing transition that
        # already succeeded.
        workspace_id = await _workspace(db_session)
        sender = _RecordingSender()
        sender.fail_with = RuntimeError("smtp is down")
        service = _service(db_session, sender)
        notification = await service.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.PAYMENT_FAILED,
            message=_message(),
            dedupe_key=f"k:{workspace_id}",
            recipient="finance@example.test",
        )
        assert notification is not None
        result = await db_session.execute(
            text("SELECT status, error FROM notification_deliveries WHERE notification_id = :id"),
            {"id": notification.id},
        )
        status_value, error = result.one()
        assert status_value == "failed"
        assert "smtp is down" in error
        await db_session.rollback()

    async def test_one_email_per_notification_even_under_retry(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        repo = SqlDeliveryRepository(db_session)
        notifications = SqlNotificationRepository(db_session)
        notification = await notifications.create(
            workspace_id=workspace_id,
            kind=NotificationKind.PAYMENT_FAILED,
            severity=Severity.CRITICAL,
            title="t",
            body="b",
            action_path=None,
            dedupe_key=f"k:{workspace_id}",
            metadata={},
        )
        assert notification is not None
        first = await repo.claim(notification_id=notification.id, address="finance@example.test")
        second = await repo.claim(notification_id=notification.id, address="finance@example.test")
        assert first is not None
        assert second is None
        await db_session.rollback()


class TestReadState:
    async def test_marking_read_removes_it_from_unread(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        notification = await service.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.PAYMENT_FAILED,
            message=_message(),
            dedupe_key=f"k:{workspace_id}",
        )
        assert notification is not None
        assert await service.unread_count(workspace_id) == 1
        assert (
            await service.mark_read(workspace_id=workspace_id, notification_id=notification.id)
            is True
        )
        assert await service.unread_count(workspace_id) == 0
        await db_session.rollback()

    async def test_marking_an_already_read_notification_reports_no_change(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        notification = await service.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.PAYMENT_FAILED,
            message=_message(),
            dedupe_key=f"k:{workspace_id}",
        )
        assert notification is not None
        await service.mark_read(workspace_id=workspace_id, notification_id=notification.id)
        assert (
            await service.mark_read(workspace_id=workspace_id, notification_id=notification.id)
            is False
        )
        await db_session.rollback()

    async def test_another_workspace_cannot_mark_it_read(self, db_session: AsyncSession) -> None:
        # Rule 11 at the query layer: the update carries `workspace_id`,
        # so a guessed id from another tenant matches nothing — and the
        # answer is identical to "not found", so it cannot be used to
        # probe for existence.
        mine = await _workspace(db_session)
        theirs = await _workspace(db_session)
        service = _service(db_session)
        notification = await service.raise_(
            workspace_id=mine,
            kind=NotificationKind.PAYMENT_FAILED,
            message=_message(),
            dedupe_key=f"k:{mine}",
        )
        assert notification is not None
        assert (
            await service.mark_read(workspace_id=theirs, notification_id=notification.id) is False
        )
        assert await service.unread_count(mine) == 1
        await db_session.rollback()

    async def test_another_workspaces_notifications_are_never_listed(
        self, db_session: AsyncSession
    ) -> None:
        mine = await _workspace(db_session)
        theirs = await _workspace(db_session)
        service = _service(db_session)
        for workspace_id in (mine, theirs, theirs):
            await service.raise_(
                workspace_id=workspace_id,
                kind=NotificationKind.PAYMENT_FAILED,
                message=_message(),
                dedupe_key=f"k:{workspace_id}:{uuid.uuid4()}",
            )
        assert len(await service.list_for(workspace_id=mine)) == 1
        await db_session.rollback()

    async def test_mark_all_read_reports_how_many_it_cleared(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        for index in range(3):
            await service.raise_(
                workspace_id=workspace_id,
                kind=NotificationKind.PAYMENT_FAILED,
                message=_message(),
                dedupe_key=f"k:{workspace_id}:{index}",
            )
        assert await service.mark_all_read(workspace_id) == 3
        assert await service.unread_count(workspace_id) == 0
        # Idempotent: a second call clears nothing rather than failing.
        assert await service.mark_all_read(workspace_id) == 0
        await db_session.rollback()

    async def test_unread_only_filters_the_list(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        first = await service.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.PAYMENT_FAILED,
            message=_message(),
            dedupe_key=f"k:{workspace_id}:1",
        )
        await service.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.PAYMENT_FAILED,
            message=_message(),
            dedupe_key=f"k:{workspace_id}:2",
        )
        assert first is not None
        await service.mark_read(workspace_id=workspace_id, notification_id=first.id)
        assert len(await service.list_for(workspace_id=workspace_id)) == 2
        assert len(await service.list_for(workspace_id=workspace_id, unread_only=True)) == 1
        await db_session.rollback()


class TestBillingNotifier:
    async def test_a_dunning_cycle_sends_one_message_per_touchpoint(
        self, db_session: AsyncSession
    ) -> None:
        # Keyed on the cycle *and* the day, so the sweep running twice on
        # day 3 sends one email while the day-7 touchpoint still gets
        # through.
        workspace_id = await _workspace(db_session)
        sender = _RecordingSender()
        notifier = BillingNotifier(notifications=_service(db_session, sender))
        first_failure = _NOW
        for day in (3, 3, 7):
            await notifier.dunning_reminder(
                workspace_id=workspace_id,
                subscription_id="sub-1",
                first_failure_at=first_failure,
                day=day,
                days_remaining=14 - day,
                deadline=_NOW,
                recipient="finance@example.test",
            )
        assert len(sender.sent) == 2
        await db_session.rollback()

    async def test_a_repeated_payment_failure_in_one_cycle_tells_the_customer_once(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        sender = _RecordingSender()
        notifier = BillingNotifier(notifications=_service(db_session, sender))
        for _ in range(3):
            await notifier.payment_failed(
                workspace_id=workspace_id,
                subscription_id="sub-1",
                amount_cents=2900,
                deadline=_NOW,
                recipient="finance@example.test",
                first_failure_at=_NOW,
            )
        assert len(sender.sent) == 1
        await db_session.rollback()

    async def test_a_quota_warning_fires_once_per_period_not_once_per_run(
        self, db_session: AsyncSession
    ) -> None:
        # Once a workspace crosses the line every subsequent run would
        # otherwise raise another one — hundreds of them.
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        notifier = BillingNotifier(notifications=service)
        for _ in range(5):
            await notifier.quota_threshold(
                workspace_id=workspace_id,
                dimension="agent_runs",
                percent=100,
                limit=10_000,
                period_start=_NOW,
                recipient="finance@example.test",
                exceeded=True,
            )
        assert len(await service.list_for(workspace_id=workspace_id)) == 1
        await db_session.rollback()

    async def test_the_approaching_and_exceeded_warnings_are_separate(
        self, db_session: AsyncSession
    ) -> None:
        # A customer who was warned at 80% still needs telling when work
        # actually stops.
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        notifier = BillingNotifier(notifications=service)
        await notifier.quota_threshold(
            workspace_id=workspace_id,
            dimension="agent_runs",
            percent=85,
            limit=10_000,
            period_start=_NOW,
            recipient="finance@example.test",
            exceeded=False,
        )
        await notifier.quota_threshold(
            workspace_id=workspace_id,
            dimension="agent_runs",
            percent=100,
            limit=10_000,
            period_start=_NOW,
            recipient="finance@example.test",
            exceeded=True,
        )
        kinds = {n.kind for n in await service.list_for(workspace_id=workspace_id)}
        assert kinds == {
            NotificationKind.QUOTA_APPROACHING,
            NotificationKind.QUOTA_EXCEEDED,
        }
        await db_session.rollback()

    async def test_a_redelivered_payment_receipt_is_recorded_once(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        service = _service(db_session)
        notifier = BillingNotifier(notifications=service)
        for _ in range(2):
            await notifier.payment_succeeded(
                workspace_id=workspace_id,
                amount_cents=2900,
                plan_name="Pro",
                provider_event_id="evt_1",
            )
        assert len(await service.list_for(workspace_id=workspace_id)) == 1
        await db_session.rollback()
