"""The test-mode / live-mode key guard.

Both directions of this mistake are silent until money is involved: a
test key in production means customers complete checkout and are never
charged while the product behaves as though they were, and a live key
outside production means a test run or a stray preview-environment
webhook can move real money. Neither raises anything on its own.

Asserted against `Settings` directly rather than through the app, so the
check is proven at the layer that owns it.
"""

from __future__ import annotations

import pytest

from agentverse_api.infrastructure.config import Settings

_BASE: dict[str, str] = {
    "database_url": "postgresql+asyncpg://u:p@localhost:5432/db",
    "auth_internal_url": "http://localhost:3000",
    "auth_public_url": "http://localhost:3000",
    "api_public_url": "http://localhost:8000",
    "internal_api_secret": "test-secret",
    "openai_api_key": "sk-test-placeholder",
}


def _settings(**overrides: object) -> Settings:
    return Settings(**{**_BASE, **overrides})  # type: ignore[arg-type]


class TestConfiguredFlag:
    def test_neither_half_means_not_configured(self) -> None:
        assert _settings().stripe_configured is False

    def test_a_secret_key_alone_is_not_configured(self) -> None:
        # A secret key without a webhook secret would take payments this
        # service could never learn the outcome of — worse than not being
        # configured at all.
        assert _settings(stripe_secret_key="sk_test_x").stripe_configured is False

    def test_both_halves_are_configured(self) -> None:
        settings = _settings(stripe_secret_key="sk_test_x", stripe_webhook_secret="whsec_x")
        assert settings.stripe_configured is True


class TestModeGuard:
    def test_a_test_key_in_production_refuses_to_start(self) -> None:
        settings = _settings(
            environment="production",
            stripe_secret_key="sk_test_x",
            stripe_webhook_secret="whsec_x",
        )
        with pytest.raises(ValueError, match="not a live-mode"):
            settings.validate_stripe_mode()

    def test_a_live_key_outside_production_refuses_to_start(self) -> None:
        settings = _settings(
            environment="development",
            stripe_secret_key="sk_live_x",
            stripe_webhook_secret="whsec_x",
        )
        with pytest.raises(ValueError, match="live-mode Stripe key"):
            settings.validate_stripe_mode()

    def test_a_live_key_in_production_is_accepted(self) -> None:
        settings = _settings(
            environment="production",
            stripe_secret_key="sk_live_x",
            stripe_webhook_secret="whsec_x",
        )
        settings.validate_stripe_mode()

    def test_a_test_key_in_development_is_accepted(self) -> None:
        settings = _settings(
            environment="development",
            stripe_secret_key="sk_test_x",
            stripe_webhook_secret="whsec_x",
        )
        settings.validate_stripe_mode()

    def test_no_key_at_all_is_accepted_everywhere(self) -> None:
        # CI, local development and preview environments legitimately run
        # with no payment provider.
        for environment in ("development", "staging", "production", "test"):
            _settings(environment=environment).validate_stripe_mode()

    def test_the_test_environment_rejects_a_live_key(self) -> None:
        # The case that matters most: a developer running the suite must
        # not be able to charge a real card.
        settings = _settings(
            environment="test",
            stripe_secret_key="sk_live_x",
            stripe_webhook_secret="whsec_x",
        )
        with pytest.raises(ValueError, match="live-mode Stripe key"):
            settings.validate_stripe_mode()


class TestApiVersionPinning:
    def test_the_api_version_is_pinned_not_latest(self) -> None:
        # Inheriting the account's dashboard default makes this service's
        # behaviour depend on a setting nobody in this repo can review.
        version = _settings().stripe_api_version
        assert version
        assert version != "latest"
