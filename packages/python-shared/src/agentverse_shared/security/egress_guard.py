"""Deny-by-default egress control for agent-initiated outbound calls.

Threat model T1. Every outbound call an agent causes — an MCP server
connection, a tool's HTTP request, a webhook fetch — passes through here.
Direct outbound sockets from worker processes are prohibited
(CLAUDE.md §10).

Three properties make this more than an IP blocklist:

**It validates every resolved address, not just the first.** A hostname
with several A records where only one is public is a trivial bypass of
a `resolve()[0]` check.

**It pins the validated address.** The caller connects to the IP this
guard approved, sending the original `Host` header — it does not hand the
hostname back to an HTTP client that would resolve it a second time. That
second resolution is DNS rebinding, and a validate-then-fetch guard does
not stop it. This is the single most important line in the file.

**It re-validates redirects.** A `302` to `169.254.169.254` is the same
attack with an extra hop, and a client following redirects on its own
never consults the guard again.

This is one of two layers. Worker egress network policy at the
infrastructure layer is the other, so a bug here is not the only thing
between an agent and the cloud metadata service (CLAUDE.md §10: defence
in depth).
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

#: Only these reach a third party. `file:`, `gopher:`, `ftp:`, and
#: friends are classic SSRF primitives; an allowlist means a scheme
#: nobody thought about is denied rather than permitted.
ALLOWED_SCHEMES = frozenset({"http", "https"})

#: Networks no agent-initiated call may reach. Deny-by-default: this is
#: applied *after* an allowlist check on scheme, and anything not
#: explicitly reachable is rejected.
_DENIED_V4 = (
    ipaddress.ip_network("0.0.0.0/8"),  # "this network"
    ipaddress.ip_network("10.0.0.0/8"),  # RFC1918
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT
    ipaddress.ip_network("127.0.0.0/8"),  # loopback
    ipaddress.ip_network("169.254.0.0/16"),  # link-local INCLUDING cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),  # RFC1918
    ipaddress.ip_network("192.0.0.0/24"),  # IETF protocol assignments
    ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1
    ipaddress.ip_network("192.168.0.0/16"),  # RFC1918
    ipaddress.ip_network("198.18.0.0/15"),  # benchmarking
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),  # multicast
    ipaddress.ip_network("240.0.0.0/4"),  # reserved, includes broadcast
)

_DENIED_V6 = (
    ipaddress.ip_network("::/128"),  # unspecified
    ipaddress.ip_network("::1/128"),  # loopback
    ipaddress.ip_network("fc00::/7"),  # unique local
    ipaddress.ip_network("fe80::/10"),  # link-local
    ipaddress.ip_network("ff00::/8"),  # multicast
    ipaddress.ip_network("2001:db8::/32"),  # documentation
    #: Cloud metadata over IPv6. Explicit because "it's IPv6, nobody
    #: uses it" is how this range gets missed.
    ipaddress.ip_network("fd00:ec2::254/128"),
)

#: A redirect chain longer than this is either a misconfiguration or an
#: attempt to exhaust the validator.
MAX_REDIRECT_HOPS = 5

#: DNS is a network call an attacker can stall. Bounded so a hostname
#: pointed at a black-holed resolver cannot hang a worker.
DNS_TIMEOUT_SECONDS = 5.0


class EgressDeniedError(Exception):
    """A destination was rejected.

    The message is safe to surface to the user and to record in
    `tool_calls.denial_reason`: it names the rule, never anything an
    attacker could not already determine by trying.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ValidatedDestination:
    """A destination the guard approved, with the address to connect to.

    Carrying the resolved IP *and* the original host is the whole point:
    the caller dials `ip` and sends `Host: host`, so no second resolution
    happens between validation and connection.
    """

    url: str
    scheme: str
    host: str
    port: int
    #: Every address the hostname resolved to. All were validated; the
    #: caller may use any, and re-resolution is unnecessary.
    addresses: tuple[str, ...]

    @property
    def primary_address(self) -> str:
        return self.addresses[0]


def _normalize(address: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Unwraps IPv4-mapped and 6to4 IPv6 forms.

    `::ffff:169.254.169.254` is the metadata address wearing a hat. A
    guard that checks the v6 tables only would pass it straight through.
    """
    parsed = ipaddress.ip_address(address)
    if isinstance(parsed, ipaddress.IPv6Address):
        if parsed.ipv4_mapped is not None:
            return parsed.ipv4_mapped
        if parsed.sixtofour is not None:
            return parsed.sixtofour
    return parsed


def is_denied_address(address: str) -> str | None:
    """Returns the rule that denies this address, or None if it is
    reachable.

    Returning the *reason* rather than a bool is deliberate: it is what
    gets recorded in `tool_calls.denial_reason`, and a bare `False` would
    make a blocked SSRF attempt unauditable.
    """
    try:
        ip = _normalize(address)
    except ValueError:
        return f"{address!r} is not a valid IP address"

    if isinstance(ip, ipaddress.IPv4Address):
        for network in _DENIED_V4:
            if ip in network:
                return f"destination {ip} is in denied range {network}"
    else:
        for network in _DENIED_V6:
            if ip in network:
                return f"destination {ip} is in denied range {network}"

    # Backstop for anything the explicit tables missed — a future
    # special-use range added to the stdlib is caught without a code
    # change here.
    if not ip.is_global:
        return f"destination {ip} is not a globally routable address"
    return None


async def _resolve(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(host, port, type=socket.SOCK_STREAM),
            timeout=DNS_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise EgressDeniedError(f"DNS lookup for {host!r} timed out") from exc
    except socket.gaierror as exc:
        raise EgressDeniedError(f"{host!r} could not be resolved") from exc

    addresses: list[str] = []
    for info in infos:
        sockaddr = info[4]
        address = str(sockaddr[0])
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise EgressDeniedError(f"{host!r} resolved to no addresses")
    return addresses


async def validate_destination(url: str) -> ValidatedDestination:
    """Approves a URL, or raises `EgressDeniedError` naming the rule.

    Every resolved address must pass. One public address among several
    private ones is not "mostly fine" — it is a hostname an attacker
    controls, and which address a client picks is not ours to predict.
    """
    parts = urlsplit(url)

    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise EgressDeniedError(
            f"scheme {parts.scheme!r} is not permitted; only {sorted(ALLOWED_SCHEMES)} are"
        )
    host = parts.hostname
    if not host:
        raise EgressDeniedError("destination URL has no host")
    # Credentials in the URL are both a leak (they land in logs) and a
    # known way to make a hostile URL read as a familiar one.
    if parts.username or parts.password:
        raise EgressDeniedError("credentials embedded in the URL are not permitted")

    port = parts.port or (443 if parts.scheme.lower() == "https" else 80)

    # A literal IP skips DNS entirely — validate it directly rather than
    # round-tripping it through the resolver.
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        addresses = await _resolve(host, port)

    for address in addresses:
        denial = is_denied_address(address)
        if denial is not None:
            raise EgressDeniedError(f"{host!r} → {denial}")

    return ValidatedDestination(
        url=url,
        scheme=parts.scheme.lower(),
        host=host,
        port=port,
        addresses=tuple(addresses),
    )


async def validate_redirect_chain(urls: list[str]) -> ValidatedDestination:
    """Validates every hop of a redirect chain and returns the final one.

    Callers must follow redirects manually — `follow_redirects=True` on an
    HTTP client hands the decision to the client, which will happily
    follow a `302` to the metadata service without asking this module.
    """
    if not urls:
        raise EgressDeniedError("empty redirect chain")
    if len(urls) > MAX_REDIRECT_HOPS:
        raise EgressDeniedError(f"redirect chain exceeded {MAX_REDIRECT_HOPS} hops")

    validated: ValidatedDestination | None = None
    for hop, url in enumerate(urls, start=1):
        try:
            validated = await validate_destination(url)
        except EgressDeniedError as exc:
            raise EgressDeniedError(f"redirect hop {hop}: {exc.reason}") from exc
    assert validated is not None  # non-empty list guaranteed above
    return validated
