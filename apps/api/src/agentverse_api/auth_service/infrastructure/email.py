"""Implements `domain.ports.EmailSender`.

Dev-only stub (Increment 5 decision, confirmed with the project owner):
logs instead of delivering — no transactional email vendor is configured
yet. `apps/web` has its own mirror of this same decision
(`lib/email/sender.ts`, used by Better Auth's `sendResetPassword`); the
two log independently rather than one calling into the other, since
neither has a real vendor to share today. Swapping in a real vendor here
is a new class behind `EmailSender`, no caller changes.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class LoggingEmailSender:
    async def send(self, *, to: str, subject: str, body: str) -> None:
        logger.info(
            "email.not_delivered — no transactional email vendor configured yet "
            "to=%s subject=%s body=%s",
            to,
            subject,
            body,
        )
