"""Official Python SDK for the AgentVerse API.

    from agentverse import AgentVerse

    with AgentVerse() as av:                # reads AGENTVERSE_API_KEY
        agent = av.agents.create(
            name="Researcher",
            model="gpt-4o-mini",
            system_instructions="Answer only from the material provided.",
        )
        run = av.runs.create(agent_id=agent["id"], input="Summarise this.")

Or install one of the first-party templates instead of writing a prompt:

    av.marketplace.install("research-assistant")

Verifying an inbound webhook does not need a client or a key:

    from agentverse.webhooks import verify_webhook
"""

from agentverse.client import AgentVerse, AsyncAgentVerse
from agentverse.errors import (
    AgentVerseError,
    APIConnectionError,
    APIError,
    AuthenticationError,
    ConfigurationError,
    Conflict,
    NotFound,
    PermissionDenied,
    RateLimited,
    ServerError,
    ServiceUnavailable,
    ValidationError,
)
from agentverse.webhooks import (
    SignatureVerificationError,
    WebhookEvent,
    verify_webhook,
)

__version__ = "0.1.0a0"

__all__ = [
    "APIConnectionError",
    "APIError",
    "AgentVerse",
    "AgentVerseError",
    "AsyncAgentVerse",
    "AuthenticationError",
    "ConfigurationError",
    "Conflict",
    "NotFound",
    "PermissionDenied",
    "RateLimited",
    "ServerError",
    "ServiceUnavailable",
    "SignatureVerificationError",
    "ValidationError",
    "WebhookEvent",
    "__version__",
    "verify_webhook",
]
