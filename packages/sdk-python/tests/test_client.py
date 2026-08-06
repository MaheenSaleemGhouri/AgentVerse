"""The client against a mocked API.

`respx` rather than a live server: what is being checked is the request
the SDK *sends* and how it treats what comes back, and both are exactly
the things a live server would obscure.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from agentverse import (
    AgentVerse,
    AsyncAgentVerse,
    AuthenticationError,
    ConfigurationError,
    Conflict,
    NotFound,
    RateLimited,
    ServerError,
    ServiceUnavailable,
    ValidationError,
)
from agentverse.errors import APIConnectionError, PermissionDenied

_BASE = "https://api.test.local"
_WORKSPACE = "ws-1"


@pytest.fixture
def client() -> AgentVerse:
    return AgentVerse(api_key="key-1", workspace_id=_WORKSPACE, base_url=_BASE, max_retries=0)


class TestConfiguration:
    def test_a_missing_key_fails_at_construction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A deployment mistake should surface at startup, not at 3am on
        # the first request.
        monkeypatch.delenv("AGENTVERSE_API_KEY", raising=False)
        with pytest.raises(ConfigurationError, match="API key"):
            AgentVerse(workspace_id=_WORKSPACE)

    def test_a_missing_workspace_fails_at_construction(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AGENTVERSE_WORKSPACE_ID", raising=False)
        with pytest.raises(ConfigurationError, match="workspace"):
            AgentVerse(api_key="key-1")

    def test_credentials_come_from_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGENTVERSE_API_KEY", "key-env")
        monkeypatch.setenv("AGENTVERSE_WORKSPACE_ID", "ws-env")
        with AgentVerse(base_url=_BASE) as av:
            assert av.workspace_id == "ws-env"

    def test_a_relative_base_url_is_refused(self) -> None:
        with pytest.raises(ConfigurationError, match="absolute"):
            AgentVerse(api_key="k", workspace_id="w", base_url="api.example.com")

    def test_an_injected_client_is_not_closed_by_us(self) -> None:
        # The caller may be sharing one pool across several SDKs.
        shared = httpx.Client()
        av = AgentVerse(api_key="k", workspace_id="w", base_url=_BASE, http_client=shared)
        av.close()
        assert not shared.is_closed
        shared.close()


class TestRequestShape:
    @respx.mock
    def test_the_api_key_is_sent_as_a_bearer_token(self, client: AgentVerse) -> None:
        route = respx.get(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents").mock(
            return_value=httpx.Response(200, json=[])
        )
        client.agents.list()
        assert route.calls.last.request.headers["Authorization"] == "Bearer key-1"

    @respx.mock
    def test_the_workspace_comes_from_the_client_not_the_call(self, client: AgentVerse) -> None:
        # Every API key is issued for one workspace; making the caller
        # repeat it invites a mismatch the server answers with a bare 404.
        route = respx.get(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents").mock(
            return_value=httpx.Response(200, json=[])
        )
        client.agents.list()
        assert _WORKSPACE in str(route.calls.last.request.url)

    @respx.mock
    def test_a_user_agent_identifies_the_sdk(self, client: AgentVerse) -> None:
        route = respx.get(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents").mock(
            return_value=httpx.Response(200, json=[])
        )
        client.agents.list()
        assert route.calls.last.request.headers["User-Agent"].startswith("agentverse-python/")

    @respx.mock
    def test_omitted_optional_fields_are_absent_not_null(self, client: AgentVerse) -> None:
        # Absent means "use the default"; null would mean "set it to
        # nothing". Sending null changes the request's meaning.
        route = respx.post(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents").mock(
            return_value=httpx.Response(201, json={"id": "a1"})
        )
        client.agents.create(name="A", model="gpt-4o-mini", system_instructions="Hi")
        import json as _json

        body = _json.loads(route.calls.last.request.content)
        assert set(body) == {"name", "model", "system_instructions"}


class TestIdempotency:
    @respx.mock
    def test_a_run_carries_an_idempotency_key_by_default(self, client: AgentVerse) -> None:
        # A run costs money, so the safe behaviour is the default rather
        # than something to remember.
        route = respx.post(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents/a1/runs").mock(
            return_value=httpx.Response(202, json={"id": "r1", "status": "queued"})
        )
        client.runs.create(agent_id="a1", input="hello")
        assert route.calls.last.request.headers["Idempotency-Key"]

    @respx.mock
    def test_a_supplied_key_is_used_verbatim(self, client: AgentVerse) -> None:
        # A queue redelivering a job should reuse the job's id, so two
        # workers cannot start the same run twice.
        route = respx.post(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents/a1/runs").mock(
            return_value=httpx.Response(202, json={"id": "r1"})
        )
        client.runs.create(agent_id="a1", input="hi", idempotency_key="job-42")
        assert route.calls.last.request.headers["Idempotency-Key"] == "job-42"

    @respx.mock
    def test_two_runs_get_different_generated_keys(self, client: AgentVerse) -> None:
        route = respx.post(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents/a1/runs").mock(
            return_value=httpx.Response(202, json={"id": "r1"})
        )
        client.runs.create(agent_id="a1", input="one")
        client.runs.create(agent_id="a1", input="two")
        keys = {call.request.headers["Idempotency-Key"] for call in route.calls}
        assert len(keys) == 2

    @respx.mock
    def test_a_read_carries_no_idempotency_key(self, client: AgentVerse) -> None:
        route = respx.get(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents").mock(
            return_value=httpx.Response(200, json=[])
        )
        client.agents.list()
        assert "Idempotency-Key" not in route.calls.last.request.headers


class TestErrorMapping:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (401, AuthenticationError),
            (403, PermissionDenied),
            (404, NotFound),
            (409, Conflict),
            (422, ValidationError),
            (429, RateLimited),
            (503, ServiceUnavailable),
        ],
    )
    @respx.mock
    def test_statuses_map_to_their_own_classes(
        self, client: AgentVerse, status: int, expected: type[Exception]
    ) -> None:
        # A caller branching on `.status_code` is doing work the SDK
        # exists to do once.
        respx.get(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents").mock(
            return_value=httpx.Response(status, json={"detail": "nope"})
        )
        with pytest.raises(expected):
            client.agents.list()

    @respx.mock
    def test_a_rate_limit_carries_retry_after(self, client: AgentVerse) -> None:
        respx.get(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents").mock(
            return_value=httpx.Response(
                429, json={"detail": {"code": "rate_limited"}}, headers={"Retry-After": "42"}
            )
        )
        with pytest.raises(RateLimited) as exc:
            client.agents.list()
        assert exc.value.retry_after == 42.0

    @respx.mock
    def test_503_is_not_reported_as_a_rate_limit(self, client: AgentVerse) -> None:
        # The API returns 503 when it cannot check your budget, which
        # means you are *not* over it. A client that logged this as a
        # rate limit would chase the wrong problem.
        respx.get(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents").mock(
            return_value=httpx.Response(503, json={"detail": "limiter down"})
        )
        with pytest.raises(ServiceUnavailable) as exc:
            client.agents.list()
        assert not isinstance(exc.value, RateLimited)

    @respx.mock
    def test_the_request_id_is_attached(self, client: AgentVerse) -> None:
        # The only thing that makes a support conversation about one
        # failed call tractable.
        respx.get(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents").mock(
            return_value=httpx.Response(
                500, json={"detail": "boom"}, headers={"X-Request-ID": "req-abc"}
            )
        )
        with pytest.raises(ServerError) as exc:
            client.agents.list()
        assert exc.value.request_id == "req-abc"

    @respx.mock
    def test_the_error_code_survives(self, client: AgentVerse) -> None:
        respx.post(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/marketplace/listings/x/install").mock(
            return_value=httpx.Response(
                422, json={"detail": {"code": "listing_not_installable", "problems": ["no model"]}}
            )
        )
        with pytest.raises(ValidationError) as exc:
            client.marketplace.install("x")
        assert exc.value.code == "listing_not_installable"

    @respx.mock
    def test_a_non_json_error_body_still_produces_an_error(self, client: AgentVerse) -> None:
        # A 502 from a proxy in front of the API is still an error the
        # caller needs to see; swallowing it for having the wrong shape
        # would turn it into "unknown".
        respx.get(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents").mock(
            return_value=httpx.Response(502, text="<html>Bad Gateway</html>")
        )
        with pytest.raises(ServerError, match="Bad Gateway"):
            client.agents.list()

    @respx.mock
    def test_a_connection_failure_is_not_an_api_error(self, client: AgentVerse) -> None:
        # There is no status code and no request id; reporting it as an
        # APIError would give callers a status of 0 to branch on.
        respx.get(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents").mock(
            side_effect=httpx.ConnectError("refused")
        )
        with pytest.raises(APIConnectionError):
            client.agents.list()


class TestResponseHandling:
    @respx.mock
    def test_a_204_does_not_raise(self, client: AgentVerse) -> None:
        # Calling `.json()` on an empty body raises; an SDK that let that
        # escape would turn every successful delete into an exception.
        respx.delete(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents/a1").mock(
            return_value=httpx.Response(204)
        )
        client.agents.delete("a1")  # must not raise

    @respx.mock
    def test_a_list_endpoint_never_returns_none(self, client: AgentVerse) -> None:
        respx.get(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/webhooks").mock(
            return_value=httpx.Response(200, json=None)
        )
        assert client.webhooks.list() == []


class TestRetryIntegration:
    @respx.mock
    def test_a_read_retries_a_500_and_succeeds(self) -> None:
        with AgentVerse(api_key="k", workspace_id=_WORKSPACE, base_url=_BASE, max_retries=2) as av:
            route = respx.get(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents").mock(
                side_effect=[
                    httpx.Response(500, json={"detail": "boom"}),
                    httpx.Response(200, json=[{"id": "a1"}]),
                ]
            )
            assert av.agents.list() == [{"id": "a1"}]
            assert route.call_count == 2

    @respx.mock
    def test_a_keyed_post_retries(self) -> None:
        with AgentVerse(api_key="k", workspace_id=_WORKSPACE, base_url=_BASE, max_retries=2) as av:
            route = respx.post(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents/a1/runs").mock(
                side_effect=[
                    httpx.Response(500, json={"detail": "boom"}),
                    httpx.Response(202, json={"id": "r1"}),
                ]
            )
            assert av.runs.create(agent_id="a1", input="x")["id"] == "r1"
            assert route.call_count == 2

    @respx.mock
    def test_an_unkeyed_post_does_not_retry_a_500(self) -> None:
        # `webhooks.create` sends no key, so a 500 must not be replayed —
        # it could have created the endpoint already.
        with AgentVerse(api_key="k", workspace_id=_WORKSPACE, base_url=_BASE, max_retries=3) as av:
            route = respx.post(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/webhooks").mock(
                return_value=httpx.Response(500, json={"detail": "boom"})
            )
            with pytest.raises(ServerError):
                av.webhooks.create(url="https://example.com/h", events=["run.completed"])
            assert route.call_count == 1


class TestAsyncClient:
    @respx.mock
    async def test_the_async_client_sends_the_same_request(self) -> None:
        route = respx.get(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents").mock(
            return_value=httpx.Response(200, json=[{"id": "a1"}])
        )
        async with AsyncAgentVerse(
            api_key="key-1", workspace_id=_WORKSPACE, base_url=_BASE, max_retries=0
        ) as av:
            assert await av.agents.list() == [{"id": "a1"}]
        assert route.calls.last.request.headers["Authorization"] == "Bearer key-1"

    @respx.mock
    async def test_the_async_client_maps_errors_identically(self) -> None:
        respx.get(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents").mock(
            return_value=httpx.Response(404, json={"detail": "nope"})
        )
        async with AsyncAgentVerse(
            api_key="k", workspace_id=_WORKSPACE, base_url=_BASE, max_retries=0
        ) as av:
            with pytest.raises(NotFound):
                await av.agents.list()

    @respx.mock
    async def test_the_async_run_also_carries_a_key(self) -> None:
        route = respx.post(f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/agents/a1/runs").mock(
            return_value=httpx.Response(202, json={"id": "r1"})
        )
        async with AsyncAgentVerse(
            api_key="k", workspace_id=_WORKSPACE, base_url=_BASE, max_retries=0
        ) as av:
            await av.runs.create(agent_id="a1", input="x")
        assert route.calls.last.request.headers["Idempotency-Key"]


class TestMarketplace:
    @respx.mock
    def test_templates_hit_the_template_route(self, client: AgentVerse) -> None:
        route = respx.get(f"{_BASE}/api/v1/marketplace/templates").mock(
            return_value=httpx.Response(200, json=[{"slug": "research-assistant"}])
        )
        assert client.marketplace.templates()[0]["slug"] == "research-assistant"
        assert route.called

    @respx.mock
    def test_the_catalog_is_not_workspace_scoped(self, client: AgentVerse) -> None:
        # The one read in this platform that is deliberately public.
        route = respx.get(f"{_BASE}/api/v1/marketplace/listings").mock(
            return_value=httpx.Response(200, json={"data": [], "total": 0})
        )
        client.marketplace.list_listings()
        assert "/workspaces/" not in str(route.calls.last.request.url)

    @respx.mock
    def test_install_targets_this_workspace(self, client: AgentVerse) -> None:
        route = respx.post(
            f"{_BASE}/api/v1/workspaces/{_WORKSPACE}/marketplace/listings/research-assistant/install"
        ).mock(return_value=httpx.Response(201, json={"agent_id": "a1", "created": True}))
        assert client.marketplace.install("research-assistant")["agent_id"] == "a1"
        assert route.called
