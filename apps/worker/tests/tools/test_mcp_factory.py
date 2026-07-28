"""Tests for MCP server construction and the guarded HTTP transport.

Two claims are worth proving here, and both are security claims:

1. **stdio is not reachable by a user-registered server.** It spawns a
   local process; a user-supplied command would be remote code execution
   on the worker fleet.
2. **Every HTTP hop is validated, including redirects.** MCP's default
   client factory sets `follow_redirects=True`, so a guard that only
   pre-flights the URL never sees the hop that matters.

No MCP server is contacted. What is under test is what AgentVerse
constructs and permits, not the protocol — that belongs to the SDK.
"""

from __future__ import annotations

import httpx
import pytest

from agentverse_worker.mcp.factory import (
    ServerConnectionSpec,
    TransportNotPermittedError,
    build_server,
    credential_placement,
)
from agentverse_worker.mcp.manager import (
    diff_tool_surface,
    infer_is_mutating,
    normalise_tools,
)
from agentverse_worker.mcp.transport import GuardedAsyncTransport, guarded_http_client_factory


def _spec(**overrides: object) -> ServerConnectionSpec:
    base: dict[str, object] = {
        "installed_server_id": "srv-1",
        "workspace_id": "ws-1",
        "display_name": "GitHub",
        "transport": "stdio",
        "command": "npx",
        "command_args": ("-y", "@modelcontextprotocol/server-github"),
        "is_catalog_entry": True,
    }
    base.update(overrides)
    return ServerConnectionSpec(**base)  # type: ignore[arg-type]


class TestStdioIsCatalogOnly:
    async def test_a_custom_server_may_not_use_stdio(self) -> None:
        """A user-supplied command would be arbitrary code execution on
        the worker fleet with extra steps (ADR-0010)."""
        with pytest.raises(TransportNotPermittedError, match="catalog"):
            await build_server(_spec(is_catalog_entry=False))

    async def test_a_catalog_entry_may(self) -> None:
        server = await build_server(_spec())
        assert server is not None

    async def test_stdio_without_a_command_is_refused(self) -> None:
        with pytest.raises(TransportNotPermittedError, match="command"):
            await build_server(_spec(command=None))

    async def test_an_unknown_transport_is_refused(self) -> None:
        with pytest.raises(TransportNotPermittedError, match="unknown transport"):
            await build_server(_spec(transport="carrier_pigeon"))


class TestHttpTransports:
    async def test_an_http_endpoint_pointing_at_metadata_is_refused(self) -> None:
        """Pre-flight is not the main control — the guarded transport
        re-checks every hop — but failing here turns "unreachable" into
        "that address is not permitted, and here is why"."""
        from agentverse_shared.security.egress_guard import EgressDeniedError

        with pytest.raises(EgressDeniedError):
            await build_server(
                _spec(
                    transport="streamable_http",
                    endpoint_url="http://169.254.169.254/mcp",
                    command=None,
                    is_catalog_entry=False,
                )
            )

    async def test_http_without_an_endpoint_is_refused(self) -> None:
        with pytest.raises(TransportNotPermittedError, match="endpoint"):
            await build_server(_spec(transport="sse", command=None, endpoint_url=None))


class TestGuardedTransport:
    def test_the_factory_installs_the_guard(self) -> None:
        """A client built without the guarded transport would validate
        nothing — the factory is the only place it gets wired in."""
        client = guarded_http_client_factory()
        assert isinstance(client._transport, GuardedAsyncTransport)  # noqa: SLF001

    def test_redirects_are_followed_but_bounded(self) -> None:
        """Following is kept on because legitimate servers redirect;
        safety comes from validating each hop, not from refusing any.
        The ceiling is lower than httpx's default of 20."""
        client = guarded_http_client_factory()
        assert client.follow_redirects is True
        assert client.max_redirects == 5

    async def test_a_request_to_a_denied_address_never_opens_a_socket(self) -> None:
        """The transport is the last thing httpx calls before it dials —
        there is no layer below it where a redirect could slip past."""
        transport = GuardedAsyncTransport()
        request = httpx.Request("GET", "http://169.254.169.254/latest/meta-data/")
        with pytest.raises(httpx.ConnectError, match="egress denied"):
            await transport.handle_async_request(request)

    async def test_the_denial_reason_survives_the_translation(self) -> None:
        """Re-raised as a ConnectError so httpx treats it as a transport
        failure — but a blocked attempt that lost its reason would be
        unauditable."""
        transport = GuardedAsyncTransport()
        request = httpx.Request("GET", "http://10.0.0.5/internal")
        with pytest.raises(httpx.ConnectError) as caught:
            await transport.handle_async_request(request)
        assert "10.0.0.0/8" in str(caught.value)


class TestCredentialPlacement:
    def test_a_bearer_token_becomes_an_authorization_header(self) -> None:
        env, headers = credential_placement("bearer_token", "TOKEN", "abc123")
        assert headers["Authorization"] == "Bearer abc123"
        assert env == {}

    def test_a_custom_header_scheme_uses_the_key_as_the_header_name(self) -> None:
        """That is what makes it custom."""
        _, headers = credential_placement("custom_header", "X-Api-Key", "abc123")
        assert headers["X-Api-Key"] == "abc123"

    def test_an_api_key_is_placed_for_both_transports(self) -> None:
        """stdio servers read API keys from the environment by
        convention; HTTP servers get a header. The caller knows the
        transport, so both are populated and the transport decides."""
        env, headers = credential_placement("api_key", "GITHUB_TOKEN", "ghp_x")
        assert env["GITHUB_TOKEN"] == "ghp_x"
        assert headers["GITHUB_TOKEN"] == "ghp_x"

    def test_an_unknown_scheme_falls_back_to_the_environment(self) -> None:
        env, headers = credential_placement("something_new", "KEY", "value")
        assert env["KEY"] == "value"
        assert headers == {}


class TestMutationInference:
    @pytest.mark.parametrize(
        "name", ["get_issue", "list_repos", "search_code", "read_file", "describe_table"]
    )
    def test_read_verbs_are_not_mutating(self, name: str) -> None:
        assert infer_is_mutating(name, "") is False

    @pytest.mark.parametrize(
        "name", ["create_issue", "delete_branch", "send_message", "merge_pull_request"]
    )
    def test_write_verbs_are_mutating(self, name: str) -> None:
        assert infer_is_mutating(name, "") is True

    def test_an_unrecognised_tool_defaults_to_mutating(self) -> None:
        """The failure directions are not symmetric: a read tool wrongly
        marked mutating is an annoyance; a write tool wrongly marked
        read-only is a read-only grant that can modify a customer's
        GitHub."""
        assert infer_is_mutating("frobnicate_widget", "") is True

    def test_a_reassuring_description_cannot_widen_access(self) -> None:
        """The description is written by the server, so a malicious one
        would describe its write tool in read-sounding language. A signal
        an attacker controls may never be used to widen access."""
        assert infer_is_mutating("obliterate_everything", "Just reads some data, honestly") is True


class TestToolNormalisation:
    def test_maps_the_sdk_shape(self) -> None:
        raw = type(
            "T",
            (),
            {
                "name": "get_issue",
                "description": "Reads one issue.",
                "inputSchema": {"type": "object"},
            },
        )()
        tools = normalise_tools([raw])
        assert tools[0].name == "get_issue"
        assert tools[0].is_mutating is False

    def test_skips_a_tool_with_no_usable_name(self) -> None:
        """A changed SDK attribute must degrade to a thinner tool list,
        not crash discovery for the whole server."""
        assert normalise_tools([object()]) == []

    def test_tolerates_a_missing_schema(self) -> None:
        raw = type("T", (), {"name": "list_things", "description": "Lists."})()
        assert normalise_tools([raw])[0].input_schema == {}


class TestToolSurfaceDiff:
    def _tool(self, name: str, schema: dict[str, object] | None = None):
        raw = type("T", (), {"name": name, "description": "x", "inputSchema": schema or {"a": 1}})()
        return normalise_tools([raw])[0]

    def test_reports_an_added_tool(self) -> None:
        before = [self._tool("get_a")]
        after = [self._tool("get_a"), self._tool("get_b")]
        assert diff_tool_surface(before, after) == ["get_b"]

    def test_reports_a_removed_tool(self) -> None:
        assert diff_tool_surface([self._tool("get_a")], []) == ["get_a"]

    def test_reports_a_changed_schema(self) -> None:
        """A breaking schema change on the server side is otherwise a
        silent runtime failure — the agent calls a tool that no longer
        accepts what it sends, and nothing says why."""
        before = [self._tool("get_a", {"a": 1})]
        after = [self._tool("get_a", {"a": 1, "b": 2})]
        assert diff_tool_surface(before, after) == ["get_a"]

    def test_reports_nothing_when_the_surface_is_stable(self) -> None:
        tools = [self._tool("get_a")]
        assert diff_tool_surface(tools, tools) == []
