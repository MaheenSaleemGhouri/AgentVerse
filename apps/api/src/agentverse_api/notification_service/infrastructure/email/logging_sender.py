"""The email adapter, deliberately not wired to a vendor yet.

Same posture as `apps/web/lib/email/sender.ts`: no transactional email
vendor is configured for this project, so this adapter logs the message
it *would* have sent instead of pretending to deliver it. That is the
honest option — a stub that silently returned success would make every
delivery test pass and every real customer email vanish, and the
failure would surface as "we never told them" during a billing dispute.

Swapping in Resend, SES or SMTP is a new class implementing
`EmailSenderPort` and one line in the composition root. No caller
changes, because no caller knows this exists.

**The body is logged in full, and that is a deliberate limit on what
this may be used for.** Transactional billing copy contains a plan name,
an amount and a date — no credentials and no agent-execution content.
If a future kind ever carries customer data, it must not use this
adapter (`logging-expert`: agent execution logs are treated as PII by
default and never land in general logs).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class LoggingEmailSender:
    """Implements `domain.ports.EmailSenderPort`."""

    async def send(self, *, to: str, subject: str, body: str) -> str | None:
        logger.info(
            "email_not_delivered_no_vendor_configured",
            extra={
                "recipient": to,
                "subject": subject,
                # Logged so the copy is reviewable end to end before a
                # vendor is connected — the alternative is discovering a
                # broken template the day real delivery is switched on.
                "body": body,
            },
        )
        # No provider message id: nothing was delivered, and inventing
        # one would make the delivery log claim a send that never
        # happened.
        return None
