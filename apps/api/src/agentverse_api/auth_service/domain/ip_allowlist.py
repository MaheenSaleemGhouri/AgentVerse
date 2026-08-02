"""Pure IP-allowlist matching — no I/O, unit-testable in isolation
(CLAUDE.md §11: permission checks are written as pure functions).
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable


def is_valid_cidr(value: str) -> bool:
    """True for a well-formed IPv4/IPv6 network or bare address.

    `strict=False` accepts a host address with a prefix (`10.0.0.5/24`)
    by masking it to its network, matching what an admin typing an
    example address expects rather than rejecting it as malformed.
    """
    try:
        ipaddress.ip_network(value, strict=False)
    except ValueError:
        return False
    return True


def is_ip_allowed(client_ip: str | None, allowed_cidrs: Iterable[str]) -> bool:
    """Whether `client_ip` falls inside any of `allowed_cidrs`.

    An **empty** allowlist allows everything: no configured entries means
    the feature was never turned on for this workspace, not that all
    access was revoked (see `WorkspaceIpAllowlist`'s docstring).

    A configured allowlist with an **unknown** client IP denies: once an
    admin has restricted access, an unidentifiable caller is not given
    the benefit of the doubt.

    An unparseable stored entry is skipped rather than raising — one bad
    row must not take down every request for the workspace, and the write
    path already validates with `is_valid_cidr`.
    """
    cidrs = list(allowed_cidrs)
    if not cidrs:
        return True
    if client_ip is None:
        return False

    try:
        address = ipaddress.ip_address(client_ip)
    except ValueError:
        return False

    for cidr in cidrs:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
        if address.version == network.version and address in network:
            return True
    return False
