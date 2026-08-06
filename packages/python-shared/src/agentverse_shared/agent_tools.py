"""The names of the built-in agent tools.

Names only — the implementations live in `apps/worker`, which is the
only place that can actually execute them.

They are here rather than there because two services need to agree on
the set and neither owns the other: the worker resolves a name to a
callable at run time, and `apps/api` has to be able to *reject* a
configuration naming a tool that will not exist when it runs. With the
set defined in the worker, `apps/api` could only either import across a
service boundary or keep a second copy that drifts — Rule 3's single
source of truth, for a list whose two copies disagreeing is invisible
until an agent runs without a capability its prompt assumes.

The worker's resolver deliberately *drops* unknown names rather than
raising, so an agent saved before a tool was withdrawn still runs. That
is right for an agent someone has been running for months, and wrong for
a curated template shipped today — which is the asymmetry this module
exists to let each side handle differently.
"""

from __future__ import annotations

from typing import Final

#: Every tool an agent may name in its configuration today.
#:
#: Deliberately short. The MCP gateway is how an agent reaches real
#: external capability; this set is the small fixed complement that
#: needs no connection, no credential and no network egress.
BUILTIN_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "get_current_time",
        "calculator",
    }
)


def unknown_tools(names: list[str]) -> list[str]:
    """The names in `names` that no built-in tool answers to.

    Returned in the order given, so an error message lists them the way
    the author wrote them.
    """
    return [name for name in names if name not in BUILTIN_TOOL_NAMES]
