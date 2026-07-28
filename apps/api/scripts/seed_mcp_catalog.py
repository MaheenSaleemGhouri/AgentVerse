"""Seeds the MCP marketplace catalog.

Run after migrations, on every deploy:

    uv run python scripts/seed_mcp_catalog.py

Idempotent by `slug` — re-running after editing an entry updates the row
rather than failing on the unique constraint, so it is safe to make this
an unconditional deploy step.

A script rather than a startup hook: seeding on boot means every replica
races to write the same rows on every restart, and a catalog edit would
only reach production when something happened to restart.
"""

from __future__ import annotations

import asyncio
import sys

from agentverse_api.infrastructure.db import get_session_factory
from agentverse_api.orchestration_service.application.seed_catalog import (
    CatalogInvalidError,
    seed_catalog,
)
from agentverse_api.orchestration_service.infrastructure.integration_repository import (
    SqlIntegrationRepository,
)


async def main() -> int:
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            count = await seed_catalog(SqlIntegrationRepository(session))
        except CatalogInvalidError as exc:
            # Non-zero so a deploy pipeline stops here. A partially
            # seeded catalog is a marketplace with holes nobody notices.
            print(f"catalog not seeded:\n{exc}", file=sys.stderr)
            return 1
    print(f"seeded {count} MCP catalog entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
