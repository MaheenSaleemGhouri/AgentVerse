"""Seeds the MCP catalog into `mcp_servers`.

Idempotent by `slug`: re-running after editing a description updates the
row rather than failing on the unique constraint. A seed that can only
run once is a seed nobody runs, and the catalog is edited far more often
than it is created.

Run at deploy time, not at import: seeding on module import would make
every process that touches this module write to the database, including
test collection.
"""

from __future__ import annotations

import logging

from agentverse_api.orchestration_service.application.mcp_catalog import (
    CATALOG,
    CatalogEntry,
    validate_catalog,
)
from agentverse_api.orchestration_service.domain.ports.integration_repository import (
    IntegrationRepository,
)

logger = logging.getLogger(__name__)


class CatalogInvalidError(Exception):
    """The catalog contradicts itself and was not seeded.

    Raised rather than seeding what is valid and skipping the rest: a
    partially-seeded catalog is a marketplace with holes nobody notices,
    and the validator's rules are exactly the ones that produce a card
    which looks installable and is not.
    """


def _to_row(entry: CatalogEntry) -> dict[str, object]:
    """Maps a catalog entry to its database row.

    `unavailable_reason` deliberately has no column: it is derived
    display text for a `custom_required` card, and storing it would mean
    two places to edit when the reason changes. The API composes it from
    `availability` at response time.
    """
    return {
        "slug": entry.slug,
        "name": entry.name,
        "description": entry.description,
        "category": entry.category,
        "transport": entry.transport,
        "availability": entry.availability,
        "auth_scheme": entry.auth_scheme,
        "command": entry.command,
        "command_args": list(entry.command_args),
        "endpoint_url": entry.endpoint_url,
        "required_credentials": list(entry.required_credentials),
        "oauth_scopes": list(entry.oauth_scopes),
        "documentation_url": entry.documentation_url,
        "icon_slug": entry.icon_slug,
        "is_deprecated": False,
    }


async def seed_catalog(repo: IntegrationRepository) -> int:
    """Upserts every catalog entry. Returns how many were written.

    Validates first and refuses the whole batch on any contradiction —
    the checks are cheap and the failure mode they prevent (an entry the
    UI offers to install that has nowhere to connect to) is one a user
    discovers rather than a test.
    """
    problems = validate_catalog()
    if problems:
        raise CatalogInvalidError(
            "the MCP catalog has unresolved problems and was not seeded:\n  - "
            + "\n  - ".join(problems)
        )

    for entry in CATALOG:
        await repo.upsert_catalog_entry(entry=_to_row(entry))

    logger.info("mcp_catalog_seeded count=%s", len(CATALOG))
    return len(CATALOG)
