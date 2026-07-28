"""Tests for the seeded MCP catalog.

The catalog is data, so the tests are consistency rules rather than
behaviour. They exist because a hand-edited row is the most likely way
this phase's security and honesty invariants get broken, and because an
entry that looks installable but cannot connect produces a marketplace
that lies to the user.
"""

from __future__ import annotations

import pytest

from agentverse_api.orchestration_service.application.mcp_catalog import (
    CATALOG,
    CatalogEntry,
    catalog_by_slug,
    validate_catalog,
)


def test_catalog_has_no_internal_contradictions() -> None:
    """The single assertion that must never be waived — every other test
    here is a more specific reading of one of these rules."""
    assert validate_catalog() == []


def test_slugs_are_unique() -> None:
    assert len(catalog_by_slug()) == len(CATALOG)


@pytest.mark.parametrize("entry", CATALOG, ids=lambda e: e.slug)
class TestEveryEntry:
    def test_declares_a_known_transport(self, entry: CatalogEntry) -> None:
        assert entry.transport in ("stdio", "sse", "streamable_http")

    def test_declares_a_known_availability(self, entry: CatalogEntry) -> None:
        assert entry.availability in ("official", "community", "custom_required")

    def test_description_is_specific_enough_to_route_on(self, entry: CatalogEntry) -> None:
        """A tool/server description is part of the prompt — a vague one
        degrades selection as much as a bad system prompt
        (`mcp-expert`)."""
        assert len(entry.description) >= 40
        assert entry.description.strip().endswith(".")

    def test_an_installable_entry_can_actually_connect(self, entry: CatalogEntry) -> None:
        """The "marketplace that lies" check: an entry the UI offers to
        install must have somewhere to connect to."""
        if entry.availability == "custom_required":
            return
        if entry.transport == "stdio":
            assert entry.command, f"{entry.slug} is installable but has no command"
        else:
            assert entry.endpoint_url, f"{entry.slug} is installable but has no endpoint_url"

    def test_an_unavailable_entry_explains_itself(self, entry: CatalogEntry) -> None:
        """A greyed-out Install button with no explanation is worse than
        no card at all."""
        if entry.availability == "custom_required":
            assert entry.unavailable_reason
            assert len(entry.unavailable_reason) >= 40

    def test_an_https_endpoint_is_never_plain_http(self, entry: CatalogEntry) -> None:
        """A catalog-seeded endpoint is ours to get right; plaintext to a
        third party would send a bearer token in the clear."""
        if entry.endpoint_url:
            assert entry.endpoint_url.startswith("https://")

    def test_an_endpoint_is_never_an_internal_address(self, entry: CatalogEntry) -> None:
        """The egress guard would block these at run time, but a seeded
        internal endpoint is a catalog bug that should never reach it."""
        if entry.endpoint_url:
            for forbidden in ("localhost", "127.0.0.1", "169.254.", "10.", "192.168."):
                assert f"//{forbidden}" not in entry.endpoint_url


class TestStdioIsConstrained:
    def test_every_stdio_command_is_a_known_launcher(self) -> None:
        """stdio spawns a process on the worker fleet. Restricting the
        command to a small set of package launchers means a catalog edit
        cannot quietly introduce an arbitrary binary."""
        launchers = {"npx", "uvx", "python", "node"}
        for entry in CATALOG:
            if entry.transport == "stdio" and entry.command:
                assert entry.command in launchers, f"{entry.slug}: unexpected command"

    def test_no_stdio_entry_smuggles_a_shell(self) -> None:
        """`sh -c "..."` in args would turn a vetted launcher back into
        arbitrary execution."""
        for entry in CATALOG:
            joined = " ".join(entry.command_args).lower()
            assert "sh -c" not in joined
            assert "&&" not in joined
            assert ";" not in joined

    def test_custom_required_entries_never_carry_a_command(self) -> None:
        """A user must supply their own remote endpoint — and a custom
        server is never permitted stdio (ADR-0010)."""
        for entry in CATALOG:
            if entry.availability == "custom_required":
                assert entry.command is None


class TestAuthConsistency:
    def test_oauth_entries_do_not_demand_a_static_credential(self) -> None:
        """An OAuth server obtains its token through the flow. Also
        asking for a pasted secret would mean two credential paths for
        one server, and the unused one would rot."""
        for entry in CATALOG:
            if entry.auth_scheme == "oauth2" and entry.availability != "custom_required":
                assert not entry.required_credentials, f"{entry.slug}: oauth2 + static credential"

    def test_non_oauth_entries_declare_no_scopes(self) -> None:
        for entry in CATALOG:
            if entry.auth_scheme != "oauth2":
                assert not entry.oauth_scopes, f"{entry.slug}: scopes without oauth2"

    def test_an_authenticated_stdio_entry_names_its_credentials(self) -> None:
        """The install screen shows these before the user confirms —
        an entry that silently needs a secret produces a connection that
        fails for no visible reason."""
        for entry in CATALOG:
            if (
                entry.transport == "stdio"
                and entry.auth_scheme == "api_key"
                and entry.availability != "custom_required"
            ):
                assert entry.required_credentials, f"{entry.slug}: api_key but no credential names"


class TestCoverage:
    def test_the_brief_s_services_are_all_represented(self) -> None:
        """Every service the phase brief named has a card — installable
        or honestly marked as needing a custom endpoint. A missing one
        would read as "not supported" when the truth is "no MCP server
        exists"."""
        expected = {
            "github",
            "gitlab",
            "slack",
            "discord",
            "notion",
            "google-drive",
            "google-docs",
            "google-sheets",
            "google-calendar",
            "gmail",
            "outlook",
            "microsoft-teams",
            "dropbox",
            "onedrive",
            "jira",
            "confluence",
            "linear",
            "clickup",
            "trello",
            "airtable",
            "hubspot",
            "salesforce",
            "stripe",
            "twilio",
            "whatsapp",
            "telegram",
            "shopify",
            "supabase",
            "postgresql",
            "mysql",
            "redis",
            "qdrant",
            "docker",
            "kubernetes",
            "aws",
            "azure",
            "google-cloud",
            "cloudflare",
        }
        assert expected <= set(catalog_by_slug())

    def test_availability_is_not_uniformly_optimistic(self) -> None:
        """If every entry claimed `official`, the field would be
        decoration. Its value is that some entries say no."""
        availabilities = {entry.availability for entry in CATALOG}
        assert "custom_required" in availabilities
        assert "official" in availabilities
