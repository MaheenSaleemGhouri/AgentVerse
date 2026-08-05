"""Notification copy and routing rules.

These assert what the *customer reads*, which is unusual for a test
suite and deliberate here: a dunning email quoting the wrong deadline is
worse than no email, and a template that silently loses its call to
action is invisible to every other kind of test.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime

from agentverse_api.notification_service.domain import templates
from agentverse_api.notification_service.domain.notification import (
    EMAIL_KINDS,
    NotificationKind,
    Severity,
    default_severity,
    wants_email,
)

_DEADLINE = datetime(2026, 8, 24, tzinfo=UTC)


class TestCoverage:
    def test_every_kind_has_a_renderer(self) -> None:
        # A kind with no template would raise at the moment a real
        # customer event fired — the worst possible time to find out.
        missing = set(NotificationKind) - set(templates.RENDERERS)
        assert not missing, f"no template for {missing}"

    def test_every_named_renderer_exists_as_a_function(self) -> None:
        for kind, name in templates.RENDERERS.items():
            renderer = getattr(templates, name, None)
            assert callable(renderer), f"{kind} names a missing renderer: {name}"

    def test_every_kind_has_a_default_severity(self) -> None:
        for kind in NotificationKind:
            assert isinstance(default_severity(kind), Severity)

    def test_every_emailed_kind_is_a_real_kind(self) -> None:
        assert set(NotificationKind) >= EMAIL_KINDS


class TestChannelRouting:
    def test_blocking_events_reach_the_inbox(self) -> None:
        # These stop work and need action outside the product, so an
        # in-app entry alone is not enough.
        for kind in (
            NotificationKind.PAYMENT_FAILED,
            NotificationKind.DUNNING_REMINDER,
            NotificationKind.QUOTA_EXCEEDED,
            NotificationKind.SUBSCRIPTION_CANCELED,
        ):
            assert wants_email(kind) is True

    def test_receipts_and_soft_nudges_stay_in_app(self) -> None:
        # A customer who is served well does not need an email every
        # month telling them nothing changed, and an 80% warning has not
        # blocked anything.
        for kind in (
            NotificationKind.PAYMENT_SUCCEEDED,
            NotificationKind.QUOTA_APPROACHING,
            NotificationKind.PLAN_CHANGED,
        ):
            assert wants_email(kind) is False

    def test_blocking_events_are_at_least_warnings(self) -> None:
        for kind in EMAIL_KINDS:
            if kind is NotificationKind.REFERRAL_REWARDED:
                continue  # good news, deliberately not urgent
            assert default_severity(kind) in (Severity.WARNING, Severity.CRITICAL)


class TestEveryTemplate:
    """Properties that must hold for all of them at once."""

    def _all_messages(self) -> list[templates.RenderedMessage]:
        return [
            templates.trial_ending(
                workspace_id="ws-1", plan_name="Pro", ends_at=_DEADLINE, price_cents=2900
            ),
            templates.payment_failed(workspace_id="ws-1", amount_cents=2900, deadline=_DEADLINE),
            templates.dunning_reminder(workspace_id="ws-1", days_remaining=3, deadline=_DEADLINE),
            templates.subscription_canceled(
                workspace_id="ws-1", plan_name="Pro", was_involuntary=True
            ),
            templates.subscription_canceled(
                workspace_id="ws-1", plan_name="Pro", was_involuntary=False
            ),
            templates.payment_succeeded(workspace_id="ws-1", amount_cents=2900, plan_name="Pro"),
            templates.plan_changed(
                workspace_id="ws-1", from_plan="pro", to_plan="team", net_cents=7000
            ),
            templates.quota_approaching(
                workspace_id="ws-1", dimension="agent_runs", percent=85, limit=10_000
            ),
            templates.quota_exceeded(workspace_id="ws-1", dimension="agent_runs", limit=10_000),
            templates.credit_granted(
                workspace_id="ws-1", amount_cents=2000, reason="Coupon WELCOME20"
            ),
            templates.referral_rewarded(workspace_id="ws-1", amount_cents=2000),
        ]

    def test_none_is_empty(self) -> None:
        for message in self._all_messages():
            assert message.title.strip()
            assert message.body.strip()
            assert message.subject.strip()
            assert message.email_body.strip()

    def test_every_email_body_carries_the_link_placeholder(self) -> None:
        # The service substitutes `{link}`. A template that dropped it
        # would send a message with no way to act on it — invisible to
        # every other test, and the whole point of the email.
        for message in self._all_messages():
            assert "{link}" in message.email_body

    def test_every_message_links_into_this_app(self) -> None:
        # Relative, so it survives a domain change and cannot become a
        # link to somewhere else.
        for message in self._all_messages():
            assert message.action_path is not None
            assert message.action_path.startswith("/dashboard/")

    def test_no_template_leaves_an_unsubstituted_placeholder(self) -> None:
        # An f-string typo produces "Your {plan} subscription" in a real
        # customer's inbox.
        for message in self._all_messages():
            for field in (message.title, message.body, message.subject):
                assert "{" not in field, f"unsubstituted placeholder in {field!r}"

    def test_every_subject_names_the_product(self) -> None:
        # A subject line competes with everything else in a mailbox.
        for message in self._all_messages():
            assert "AgentVerse" in message.subject


class TestBillingCopy:
    def test_payment_failed_states_the_deadline_not_a_vague_warning(self) -> None:
        # A customer who knows service stops on the 24th can act; one
        # told "there was a problem" cannot.
        message = templates.payment_failed(
            workspace_id="ws-1", amount_cents=2900, deadline=_DEADLINE
        )
        assert "24 August 2026" in message.body
        assert "24 August 2026" in message.email_body

    def test_payment_failed_states_the_amount(self) -> None:
        message = templates.payment_failed(
            workspace_id="ws-1", amount_cents=2900, deadline=_DEADLINE
        )
        assert "$29.00" in message.body

    def test_a_dunning_reminder_does_not_repeat_the_first_message(self) -> None:
        # A customer who gets the identical email three times learns to
        # ignore it.
        first = templates.payment_failed(workspace_id="ws-1", amount_cents=2900, deadline=_DEADLINE)
        later = templates.dunning_reminder(
            workspace_id="ws-1", days_remaining=3, deadline=_DEADLINE
        )
        assert first.subject != later.subject
        assert first.body != later.body

    def test_the_final_reminder_reads_as_today_rather_than_in_one_day(self) -> None:
        message = templates.dunning_reminder(
            workspace_id="ws-1", days_remaining=1, deadline=_DEADLINE
        )
        assert "today" in message.subject

    def test_involuntary_cancellation_does_not_thank_the_customer(self) -> None:
        # Someone whose card expired did not choose to leave.
        message = templates.subscription_canceled(
            workspace_id="ws-1", plan_name="Pro", was_involuntary=True
        )
        assert "as requested" not in message.email_body
        assert "payment" in message.email_body

    def test_voluntary_cancellation_does_not_blame_a_payment(self) -> None:
        message = templates.subscription_canceled(
            workspace_id="ws-1", plan_name="Pro", was_involuntary=False
        )
        assert "as requested" in message.email_body

    def test_both_cancellations_say_nothing_was_deleted(self) -> None:
        # The single most reassuring fact, and the one a customer will
        # otherwise write in to ask.
        for involuntary in (True, False):
            message = templates.subscription_canceled(
                workspace_id="ws-1", plan_name="Pro", was_involuntary=involuntary
            )
            assert "deleted" in message.email_body

    def test_a_downgrade_reports_a_credit_not_a_charge(self) -> None:
        message = templates.plan_changed(
            workspace_id="ws-1", from_plan="team", to_plan="pro", net_cents=-3500
        )
        assert "credited" in message.body
        assert "$35.00" in message.body

    def test_an_upgrade_reports_what_is_due(self) -> None:
        message = templates.plan_changed(
            workspace_id="ws-1", from_plan="pro", to_plan="team", net_cents=7000
        )
        assert "due" in message.body
        assert "$70.00" in message.body

    def test_a_zero_net_change_says_so_rather_than_showing_zero(self) -> None:
        message = templates.plan_changed(
            workspace_id="ws-1", from_plan="pro", to_plan="pro", net_cents=0
        )
        assert "no change" in message.body.lower()

    def test_quota_exceeded_says_requests_are_being_refused(self) -> None:
        # The actionable fact: work is blocked right now.
        message = templates.quota_exceeded(
            workspace_id="ws-1", dimension="agent_runs", limit=10_000
        )
        assert "refused" in message.email_body
        assert "10,000" in message.email_body

    def test_dimension_keys_are_humanised_in_customer_copy(self) -> None:
        message = templates.quota_exceeded(
            workspace_id="ws-1", dimension="agent_runs", limit=10_000
        )
        assert "agent_runs" not in message.title
        assert "agent runs" in message.title


class TestPurity:
    def test_no_template_reads_a_clock(self) -> None:
        # Every claim must be a fact the caller passed in. A template
        # that read `now()` could quote a date the caller never
        # computed, which is how a dunning email promises time the
        # customer does not have.
        for name in templates.RENDERERS.values():
            source = inspect.getsource(getattr(templates, name))
            assert "now()" not in source
            assert "utcnow" not in source
