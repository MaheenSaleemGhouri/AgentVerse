"""Pure-function tests for the IP allowlist matcher — no I/O
(CLAUDE.md §11: permission logic tested in isolation).
"""

from __future__ import annotations

import pytest

from agentverse_api.auth_service.domain.ip_allowlist import is_ip_allowed, is_valid_cidr


@pytest.mark.parametrize(
    "value",
    ["10.0.0.0/8", "192.168.1.1", "0.0.0.0/0", "2001:db8::/32", "::1", "10.0.0.5/24"],
)
def test_is_valid_cidr_accepts_real_networks_and_addresses(value: str) -> None:
    assert is_valid_cidr(value)


@pytest.mark.parametrize("value", ["", "not-an-ip", "10.0.0.0/33", "999.1.1.1", "10.0.0.0/-1"])
def test_is_valid_cidr_rejects_malformed_values(value: str) -> None:
    assert not is_valid_cidr(value)


def test_empty_allowlist_allows_everything() -> None:
    """A workspace that never configured the feature is unrestricted —
    the invariant that keeps every pre-existing workspace unaffected."""
    assert is_ip_allowed("203.0.113.9", [])
    assert is_ip_allowed(None, [])


def test_configured_allowlist_allows_an_address_inside_the_range() -> None:
    assert is_ip_allowed("10.1.2.3", ["10.0.0.0/8"])


def test_configured_allowlist_denies_an_address_outside_every_range() -> None:
    assert not is_ip_allowed("203.0.113.9", ["10.0.0.0/8", "192.168.0.0/16"])


def test_configured_allowlist_denies_an_unknown_client_ip() -> None:
    """Once restricted, an unidentifiable caller gets no benefit of the
    doubt — the opposite of the empty-allowlist case above."""
    assert not is_ip_allowed(None, ["10.0.0.0/8"])


def test_a_single_matching_range_is_enough() -> None:
    assert is_ip_allowed("192.168.5.5", ["10.0.0.0/8", "192.168.0.0/16"])


def test_ipv4_address_does_not_match_an_ipv6_range() -> None:
    assert not is_ip_allowed("10.0.0.1", ["2001:db8::/32"])


def test_ipv6_address_matches_an_ipv6_range() -> None:
    assert is_ip_allowed("2001:db8::1", ["2001:db8::/32"])


def test_an_unparseable_stored_entry_is_skipped_not_fatal() -> None:
    """One bad row must not take every request down for the workspace."""
    assert is_ip_allowed("10.0.0.1", ["garbage", "10.0.0.0/8"])
    assert not is_ip_allowed("203.0.113.9", ["garbage"])


def test_a_malformed_client_ip_is_denied_when_restricted() -> None:
    assert not is_ip_allowed("not-an-ip", ["10.0.0.0/8"])
