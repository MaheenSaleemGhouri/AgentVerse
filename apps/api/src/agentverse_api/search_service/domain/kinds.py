"""What search can find, and how much of it."""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class SearchKind(StrEnum):
    """The entity kinds search covers.

    Deliberately not "everything with a name". Runs are absent because
    there is still no read path over `agent_runs` (the Phase 4 gap
    `feature-availability.ts` tracks as `runHistory`) — adding a kind
    whose results could not be opened would be a worse experience than
    not offering it.
    """

    AGENT = "agent"
    KNOWLEDGE_BASE = "knowledge_base"
    TEAM = "team"
    LISTING = "listing"


#: Per kind, not overall. A palette showing five of each reads better
#: than twenty of whichever kind happened to rank highest — ranks are
#: only comparable within a kind, since they come from different columns.
DEFAULT_LIMIT_PER_KIND: Final[int] = 5

#: The ceiling a caller may ask for. Search is a typeahead, and a
#: typeahead that returns hundreds of rows is a list endpoint wearing a
#: disguise — those exist per entity and are the right tool for that job.
MAX_LIMIT_PER_KIND: Final[int] = 25
