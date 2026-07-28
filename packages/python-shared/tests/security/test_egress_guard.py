"""Adversarial tests for the egress guard.

These are written from the attacker's side, not the happy path. Threat
model T1 names SSRF to the cloud metadata service as the highest-value
target on this surface, and every bypass technique below is one that has
worked against real deployments — a guard that only blocks `10.0.0.0/8`
and `127.0.0.1` is not a control, it is a speed bump.

DNS is stubbed rather than hit: a test that depends on a real resolver is
flaky, and what is under test is the guard's decision, not the network.
"""

from __future__ import annotations

import socket
from typing import Any

import pytest

from agentverse_shared.security import egress_guard
from agentverse_shared.security.egress_guard import (
    EgressDeniedError,
    is_denied_address,
    validate_destination,
    validate_redirect_chain,
)


@pytest.fixture
def resolves(monkeypatch: pytest.MonkeyPatch):
    """Stubs DNS so a hostname resolves to whatever the test dictates."""

    def _install(mapping: dict[str, list[str]]) -> None:
        async def fake_getaddrinfo(host: str, port: int, **_: Any) -> list[Any]:
            addresses = mapping.get(host)
            if addresses is None:
                raise socket.gaierror(f"no stub for {host}")
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))
                for address in addresses
            ]

        class _Loop:
            async def getaddrinfo(self, host: str, port: int, **kwargs: Any) -> list[Any]:
                return await fake_getaddrinfo(host, port, **kwargs)

        monkeypatch.setattr(egress_guard.asyncio, "get_running_loop", lambda: _Loop())

    return _install


class TestDeniedRanges:
    @pytest.mark.parametrize(
        "address",
        [
            "127.0.0.1",
            "127.1.1.1",
            "0.0.0.0",
            "10.0.0.5",
            "172.16.0.1",
            "172.31.255.254",
            "192.168.1.1",
            "100.64.0.1",
            "169.254.1.1",
            "224.0.0.1",
            "255.255.255.255",
        ],
    )
    def test_denies_private_and_special_ipv4(self, address: str) -> None:
        assert is_denied_address(address) is not None

    def test_denies_the_cloud_metadata_address(self) -> None:
        """The single highest-value SSRF target: it returns IAM role
        credentials to anything that can reach it."""
        denial = is_denied_address("169.254.169.254")
        assert denial is not None
        assert "169.254" in denial

    @pytest.mark.parametrize(
        "address",
        ["::1", "fe80::1", "fc00::1", "fd00::1", "ff02::1", "fd00:ec2::254"],
    )
    def test_denies_ipv6_equivalents(self, address: str) -> None:
        """ "It's IPv6, nobody uses it" is how these ranges get missed."""
        assert is_denied_address(address) is not None

    @pytest.mark.parametrize(
        "address",
        ["::ffff:169.254.169.254", "::ffff:127.0.0.1", "::ffff:10.0.0.1"],
    )
    def test_denies_ipv4_mapped_ipv6_forms(self, address: str) -> None:
        """`::ffff:169.254.169.254` is the metadata address wearing a hat.
        A guard checking only the v6 tables passes it straight through."""
        assert is_denied_address(address) is not None

    def test_denies_6to4_wrapped_private_address(self) -> None:
        # 2002:0a00:0001:: unwraps to 10.0.0.1
        assert is_denied_address("2002:a00:1::") is not None

    def test_allows_a_genuinely_public_address(self) -> None:
        assert is_denied_address("93.184.216.34") is None

    def test_rejects_a_non_address(self) -> None:
        assert is_denied_address("not-an-ip") is not None


class TestSchemeAndUrlShape:
    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "gopher://evil.test/_GET",
            "ftp://evil.test/x",
            "dict://127.0.0.1:11211/stat",
            "jar:http://evil.test!/",
        ],
    )
    async def test_denies_non_http_schemes(self, url: str) -> None:
        """An allowlist means a scheme nobody thought about is denied
        rather than permitted."""
        with pytest.raises(EgressDeniedError, match="scheme"):
            await validate_destination(url)

    async def test_denies_credentials_embedded_in_the_url(self, resolves) -> None:
        """Both a leak (they land in logs) and a known way to make a
        hostile URL read as a familiar one."""
        resolves({"evil.test": ["93.184.216.34"]})
        with pytest.raises(EgressDeniedError, match="credentials"):
            await validate_destination("https://api.github.com@evil.test/")

    async def test_denies_a_url_with_no_host(self) -> None:
        with pytest.raises(EgressDeniedError, match="no host"):
            await validate_destination("https:///path")


class TestResolution:
    async def test_denies_a_hostname_resolving_to_the_metadata_ip(self, resolves) -> None:
        """The classic bypass: a public hostname whose A record points at
        an internal address."""
        resolves({"metadata.evil.test": ["169.254.169.254"]})
        with pytest.raises(EgressDeniedError, match="169.254"):
            await validate_destination("http://metadata.evil.test/latest/meta-data/")

    async def test_denies_when_any_resolved_address_is_private(self, resolves) -> None:
        """One public address among several private ones is not "mostly
        fine" — which address a client picks is not ours to predict."""
        resolves({"mixed.test": ["93.184.216.34", "10.0.0.5"]})
        with pytest.raises(EgressDeniedError):
            await validate_destination("https://mixed.test/")

    async def test_returns_every_validated_address_for_pinning(self, resolves) -> None:
        """The caller dials a validated IP and sends the original Host —
        it never re-resolves. That second resolution is DNS rebinding,
        and returning the addresses is what makes pinning possible."""
        resolves({"good.test": ["93.184.216.34", "93.184.216.35"]})
        destination = await validate_destination("https://good.test/api")
        assert destination.addresses == ("93.184.216.34", "93.184.216.35")
        assert destination.host == "good.test"
        assert destination.port == 443

    async def test_defaults_the_port_by_scheme(self, resolves) -> None:
        resolves({"good.test": ["93.184.216.34"]})
        assert (await validate_destination("http://good.test/")).port == 80

    async def test_honours_an_explicit_port(self, resolves) -> None:
        resolves({"good.test": ["93.184.216.34"]})
        assert (await validate_destination("https://good.test:8443/")).port == 8443

    async def test_validates_a_literal_ip_without_dns(self) -> None:
        """A literal IP skips the resolver entirely — round-tripping it
        would be a second chance to get the answer wrong."""
        with pytest.raises(EgressDeniedError, match="169.254"):
            await validate_destination("http://169.254.169.254/")

    async def test_denies_an_unresolvable_host(self, resolves) -> None:
        resolves({})
        with pytest.raises(EgressDeniedError, match="resolved"):
            await validate_destination("https://nowhere.test/")


class TestRedirects:
    async def test_denies_a_redirect_to_the_metadata_ip(self, resolves) -> None:
        """A 302 to 169.254.169.254 is the same attack with an extra hop.
        A client following redirects itself never consults the guard
        again — which is why callers must follow them manually."""
        resolves({"start.test": ["93.184.216.34"]})
        with pytest.raises(EgressDeniedError, match="redirect hop 2"):
            await validate_redirect_chain(
                ["https://start.test/", "http://169.254.169.254/latest/meta-data/"]
            )

    async def test_allows_a_fully_public_chain(self, resolves) -> None:
        resolves({"a.test": ["93.184.216.34"], "b.test": ["93.184.216.35"]})
        final = await validate_redirect_chain(["https://a.test/", "https://b.test/"])
        assert final.host == "b.test"

    async def test_denies_an_over_long_chain(self, resolves) -> None:
        resolves({"a.test": ["93.184.216.34"]})
        with pytest.raises(EgressDeniedError, match="hops"):
            await validate_redirect_chain(["https://a.test/"] * 10)

    async def test_denies_an_empty_chain(self) -> None:
        with pytest.raises(EgressDeniedError):
            await validate_redirect_chain([])


class TestDenialReasons:
    async def test_the_reason_names_the_rule(self, resolves) -> None:
        """The reason is recorded in `tool_calls.denial_reason`. A bare
        boolean would make a blocked SSRF attempt unauditable, which is
        most of the control's value."""
        resolves({"evil.test": ["10.1.2.3"]})
        with pytest.raises(EgressDeniedError) as caught:
            await validate_destination("https://evil.test/")
        assert "10.1.2.3" in caught.value.reason
        assert "10.0.0.0/8" in caught.value.reason
