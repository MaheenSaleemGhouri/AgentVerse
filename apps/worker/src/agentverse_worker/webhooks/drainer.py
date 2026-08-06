"""Delivers queued webhooks to customer endpoints.

Structured like `retention/sweep.py` — a long-lived task cancelled on
shutdown, a fresh session per cycle — with one deliberate difference: no
distributed lock. Retention sweeps the whole table and two replicas doing
it at once is wasted work; delivery is a queue, and several replicas
draining it in parallel is the point. `FOR UPDATE SKIP LOCKED` is what
makes that safe: each replica claims rows nobody else holds, and none of
them blocks waiting for the others.

**Every request goes through the egress guard.** The URL is
customer-supplied, so this is an SSRF surface (Rule 6). It was validated
when it was saved, and it is validated again here, because a hostname
that resolved to a public address in March can resolve to
`169.254.169.254` today. The guard hands back a pinned IP and the
connection is made to that address with the original `Host` header —
resolving the name a second time inside the HTTP client is exactly the
DNS-rebinding hole the guard exists to close.

**Redirects are not followed.** A 3xx from a webhook endpoint is not
success and is not a destination: following it would send a signed
payload somewhere the guard never approved.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from agentverse_shared.security.egress_guard import EgressDeniedError, validate_destination
from agentverse_shared.security.envelope import CredentialVault, KeyRing, SealedSecret
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_worker.infrastructure.config import Settings
from agentverse_worker.infrastructure.db import get_session
from agentverse_worker.webhooks.tables import (
    webhook_deliveries_table,
    webhook_endpoints_table,
)

logger = logging.getLogger(__name__)

#: Mirrors apps/api's `webhook_service.domain.signing`. Duplicated
#: deliberately and asserted equal by a test rather than imported: the
#: two services do not share code, and a wire contract copied with a
#: test guarding it is the pattern already used for `mcp/tables.py`.
SIGNATURE_HEADER = "AgentVerse-Signature"
SIGNATURE_VERSION = "v1"
MAX_ATTEMPTS = 6
_BACKOFF_SECONDS: tuple[int, ...] = (10, 60, 300, 900, 3_600)
FAILURE_THRESHOLD = 20

#: A customer endpoint gets ten seconds. Longer means one slow receiver
#: holds a drainer slot while the queue behind it grows; a webhook
#: receiver that cannot acknowledge in ten seconds should be queueing
#: internally, which is what the retry schedule gives them room to do.
REQUEST_TIMEOUT_SECONDS = 10.0

#: Stored error text is truncated. An endpoint returning a megabyte of
#: HTML on every failure would otherwise put it in this table six times.
MAX_ERROR_CHARS = 2_000


@dataclass(frozen=True, slots=True)
class DueDelivery:
    id: str
    workspace_id: str
    endpoint_id: str
    event_type: str
    payload: dict[str, object]
    attempts: int
    url: str
    sealed: SealedSecret
    consecutive_failures: int


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    delivery_id: str
    delivered: bool
    response_status: int | None
    attempts: int


def backoff_seconds(attempt: int) -> int:
    """Seconds to wait before attempt `attempt` (1-based).

    Unjittered here; the caller adds spread. Kept separate so the
    schedule is readable and a change to it is a visible diff.
    """
    index = min(attempt, len(_BACKOFF_SECONDS)) - 1
    return _BACKOFF_SECONDS[max(index, 0)]


def should_retry(*, attempts_made: int, response_status: int | None) -> bool:
    """Mirrors apps/api's rule; see `webhook_service.domain.signing`.

    A 4xx other than 408/429 means the endpoint has rejected the request
    itself — the same bytes will be rejected the same way in an hour, so
    retrying is noise for both sides.
    """
    if attempts_made >= MAX_ATTEMPTS:
        return False
    if response_status is None:
        return True
    if response_status in (408, 429):
        return True
    return not 400 <= response_status < 500


class WebhookDeliveryRepository:
    """The queue operations one cycle needs, over a single session."""

    def __init__(self, session: AsyncSession, vault: CredentialVault) -> None:
        self._session = session
        self._vault = vault

    async def claim_due(self, *, limit: int) -> list[DueDelivery]:
        """Claim up to `limit` deliveries that are due, atomically.

        `FOR UPDATE SKIP LOCKED` is what lets several replicas drain the
        same table without coordinating: each takes rows nobody else
        holds, and none of them waits. Rows are moved to `delivering` in
        the same transaction, so a replica that dies mid-flight leaves
        them visibly stuck rather than silently claimed forever — a state
        the requeue below recovers.
        """
        now = datetime.now(UTC)
        claimed = (
            select(webhook_deliveries_table.c.id)
            .where(
                webhook_deliveries_table.c.status == "pending",
                webhook_deliveries_table.c.next_attempt_at <= now,
            )
            .order_by(webhook_deliveries_table.c.next_attempt_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        ids = [str(row[0]) for row in (await self._session.execute(claimed)).all()]
        if not ids:
            return []

        await self._session.execute(
            update(webhook_deliveries_table)
            .where(webhook_deliveries_table.c.id.in_(ids))
            .values(status="delivering", updated_at=now)
        )

        rows = await self._session.execute(
            select(
                webhook_deliveries_table.c.id,
                webhook_deliveries_table.c.workspace_id,
                webhook_deliveries_table.c.endpoint_id,
                webhook_deliveries_table.c.event_type,
                webhook_deliveries_table.c.payload,
                webhook_deliveries_table.c.attempts,
                webhook_endpoints_table.c.url,
                webhook_endpoints_table.c.secret_ciphertext,
                webhook_endpoints_table.c.wrapped_dek,
                webhook_endpoints_table.c.key_version,
                webhook_endpoints_table.c.consecutive_failures,
            )
            .join(
                webhook_endpoints_table,
                webhook_endpoints_table.c.id == webhook_deliveries_table.c.endpoint_id,
            )
            .where(webhook_deliveries_table.c.id.in_(ids))
        )
        await self._session.commit()

        return [
            DueDelivery(
                id=str(row[0]),
                workspace_id=str(row[1]),
                endpoint_id=str(row[2]),
                event_type=str(row[3]),
                payload=dict(row[4] or {}),
                attempts=int(row[5]),
                url=str(row[6]),
                sealed=SealedSecret(
                    ciphertext=bytes(row[7]),
                    wrapped_dek=bytes(row[8]),
                    key_version=str(row[9]),
                ),
                consecutive_failures=int(row[10]),
            )
            for row in rows.all()
        ]

    def open_secret(self, delivery: DueDelivery) -> str:
        return self._vault.open(
            delivery.sealed,
            associated_data=f"webhook:{delivery.workspace_id}:{delivery.endpoint_id}".encode(),
        )

    async def record(
        self,
        *,
        delivery: DueDelivery,
        delivered: bool,
        response_status: int | None,
        error: str | None,
    ) -> None:
        """Write the attempt's outcome and schedule or close the delivery."""
        now = datetime.now(UTC)
        attempts = delivery.attempts + 1
        retry = not delivered and should_retry(
            attempts_made=attempts, response_status=response_status
        )

        values: dict[str, object] = {
            "attempts": attempts,
            "last_response_status": response_status,
            "last_error": (error or "")[:MAX_ERROR_CHARS] or None,
            "updated_at": now,
        }
        if delivered:
            values["status"] = "delivered"
            values["delivered_at"] = now
        elif retry:
            values["status"] = "pending"
            values["next_attempt_at"] = now + timedelta(seconds=backoff_seconds(attempts))
        else:
            values["status"] = "failed"

        await self._session.execute(
            update(webhook_deliveries_table)
            .where(webhook_deliveries_table.c.id == delivery.id)
            .values(**values)
        )

        # Reset on success rather than decay: an endpoint that answered
        # is working now, and carrying old failures forward would
        # eventually disable a healthy URL that had a bad week.
        failures = 0 if delivered else delivery.consecutive_failures + 1
        endpoint_values: dict[str, object] = {"consecutive_failures": failures}
        if failures >= FAILURE_THRESHOLD:
            endpoint_values["is_active"] = False
            endpoint_values["disabled_at"] = now
            endpoint_values["disabled_reason"] = (
                f"Disabled automatically after {failures} consecutive delivery failures."
            )
        await self._session.execute(
            update(webhook_endpoints_table)
            .where(webhook_endpoints_table.c.id == delivery.endpoint_id)
            .values(**endpoint_values)
        )
        await self._session.commit()

    async def requeue_stuck(self, *, older_than_seconds: int) -> int:
        """Return abandoned `delivering` rows to `pending`.

        A replica killed mid-delivery leaves its claims in `delivering`
        with nothing to move them. Without this they are invisible to the
        queue forever — the failure being silent, which is worse than
        a duplicate delivery.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=older_than_seconds)
        result = await self._session.execute(
            update(webhook_deliveries_table)
            .where(
                webhook_deliveries_table.c.status == "delivering",
                webhook_deliveries_table.c.updated_at < cutoff,
            )
            .values(status="pending", next_attempt_at=datetime.now(UTC))
            .returning(webhook_deliveries_table.c.id)
        )
        requeued = len(result.all())
        await self._session.commit()
        return requeued


async def deliver_one(
    *, client: httpx.AsyncClient, delivery: DueDelivery, secret: str, body: str
) -> tuple[bool, int | None, str | None]:
    """One attempt. Returns `(delivered, status, error)`.

    Validates the destination immediately before connecting and pins the
    approved address, so a hostname that has since started resolving to a
    private range cannot be reached even though it passed at save time.
    """
    from agentverse_worker.webhooks.signing import signature_header

    try:
        destination = await validate_destination(delivery.url)
    except EgressDeniedError as exc:
        # Not retryable, and not the customer's server's fault — the URL
        # itself is not somewhere this platform will call.
        return False, None, f"egress denied: {exc}"

    timestamp = int(time.time())
    headers = {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: signature_header(secret=secret, timestamp=timestamp, body=body),
        "AgentVerse-Event": delivery.event_type,
        "AgentVerse-Delivery": delivery.id,
        "User-Agent": "AgentVerse-Webhooks/1.0",
    }
    try:
        response = await client.post(
            destination.pinned_url,
            content=body.encode("utf-8"),
            headers={**headers, "Host": destination.host},
            timeout=REQUEST_TIMEOUT_SECONDS,
            # Never follow: a 3xx is not success, and following one would
            # send a signed payload to an address the guard never saw.
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        return False, None, str(exc)

    return 200 <= response.status_code < 300, response.status_code, None


RepoFactory = Callable[[], AbstractAsyncContextManager[WebhookDeliveryRepository]]


class WebhookDrainer:
    def __init__(
        self,
        *,
        repo_factory: RepoFactory,
        interval_seconds: float,
        batch_size: int,
        stuck_after_seconds: int = 300,
    ) -> None:
        self._repo_factory = repo_factory
        self._interval_seconds = interval_seconds
        self._batch_size = batch_size
        self._stuck_after_seconds = stuck_after_seconds
        self._stopping = asyncio.Event()

    def stop(self) -> None:
        self._stopping.set()

    async def run_forever(self) -> None:
        while not self._stopping.is_set():
            try:
                await self.run_once()
            except Exception:
                # One bad cycle must not end delivery permanently — the
                # next interval tries again.
                logger.exception("webhook_drain_cycle_failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval_seconds)

    async def run_once(self) -> list[DeliveryResult]:
        from agentverse_worker.webhooks.signing import serialize_body

        async with self._repo_factory() as repo:
            await repo.requeue_stuck(older_than_seconds=self._stuck_after_seconds)
            due = await repo.claim_due(limit=self._batch_size)
            if not due:
                return []

            results: list[DeliveryResult] = []
            async with httpx.AsyncClient(follow_redirects=False) as client:
                for delivery in due:
                    body = serialize_body(delivery.payload)
                    try:
                        secret = repo.open_secret(delivery)
                    except Exception as exc:  # noqa: BLE001 - narrowed by the message
                        # An unreadable secret is a key-management
                        # problem, not the customer's endpoint failing.
                        # Recorded as an error so it surfaces, and
                        # retried, because a rotation in flight resolves
                        # itself.
                        logger.error(
                            "webhook_secret_unreadable delivery_id=%s error=%s",
                            delivery.id,
                            exc,
                        )
                        await repo.record(
                            delivery=delivery,
                            delivered=False,
                            response_status=None,
                            error=f"signing secret unreadable: {exc}",
                        )
                        continue

                    delivered, status_code, error = await deliver_one(
                        client=client, delivery=delivery, secret=secret, body=body
                    )
                    await repo.record(
                        delivery=delivery,
                        delivered=delivered,
                        response_status=status_code,
                        error=error,
                    )
                    results.append(
                        DeliveryResult(
                            delivery_id=delivery.id,
                            delivered=delivered,
                            response_status=status_code,
                            attempts=delivery.attempts + 1,
                        )
                    )
            return results


def build_webhook_drainer(settings: Settings) -> WebhookDrainer:
    vault = CredentialVault(KeyRing.from_env())

    @asynccontextmanager
    async def _repo_factory() -> AsyncIterator[WebhookDeliveryRepository]:
        async with get_session() as session:
            yield WebhookDeliveryRepository(session, vault)

    return WebhookDrainer(
        repo_factory=_repo_factory,
        interval_seconds=settings.webhook_drain_interval_seconds,
        batch_size=settings.webhook_drain_batch_size,
    )
