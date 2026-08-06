"""Sanitising a snapshot on its way into someone else's workspace.

These are the tests that matter most in M2. A version snapshot was
authored by a stranger and is about to become an agent that runs on the
installer's account, so every field it carries is untrusted until this
function has looked at it.
"""

from __future__ import annotations

import pytest

from agentverse_api.marketplace_service.domain.install import (
    MAX_MODEL_NAME,
    MAX_OUTPUT_TOKENS_CEILING,
    MAX_SYSTEM_INSTRUCTIONS,
    MAX_TOOLS,
    ImportedConfig,
    UninstallableConfigError,
    is_upgrade,
    sanitize_config,
)

_VALID: dict[str, object] = {
    "model": "gpt-4o-mini",
    "system_instructions": "You research things and cite your sources.",
    "temperature": 0.4,
    "max_output_tokens": 2_000,
    "tools": ["web_search"],
}


class TestCrossTenantFields:
    def test_the_publishers_knowledge_bases_never_cross_the_boundary(self) -> None:
        # The important one. Those ids name knowledge bases in the
        # *publisher's* workspace — meaningless in the installer's at
        # best, a cross-tenant reference at worst.
        config = sanitize_config({**_VALID, "knowledge_base_ids": ["kb-belonging-to-someone-else"]})
        assert not hasattr(config, "knowledge_base_ids")

    def test_unknown_fields_are_dropped_rather_than_carried(self) -> None:
        # A field added to agent configuration later must not ride into
        # another workspace through an old snapshot until someone decides
        # it should.
        config = sanitize_config({**_VALID, "some_future_field": {"nested": True}})
        assert config == ImportedConfig(
            model="gpt-4o-mini",
            system_instructions="You research things and cite your sources.",
            temperature=0.4,
            max_output_tokens=2_000,
            tools=["web_search"],
        )


class TestModel:
    def test_a_snapshot_with_no_model_cannot_be_installed(self) -> None:
        with pytest.raises(UninstallableConfigError) as exc:
            sanitize_config({"system_instructions": "hello"})
        assert any("names no model" in problem for problem in exc.value.problems)

    def test_a_blank_model_is_refused(self) -> None:
        with pytest.raises(UninstallableConfigError):
            sanitize_config({**_VALID, "model": "   "})

    def test_a_non_string_model_is_refused(self) -> None:
        with pytest.raises(UninstallableConfigError):
            sanitize_config({**_VALID, "model": {"name": "gpt-4o"}})

    def test_an_absurdly_long_model_name_is_refused(self) -> None:
        with pytest.raises(UninstallableConfigError):
            sanitize_config({**_VALID, "model": "x" * (MAX_MODEL_NAME + 1)})


class TestPromptText:
    def test_system_instructions_are_capped(self) -> None:
        # §7: every free-text field that reaches an LLM prompt has an
        # enforced size cap. Uncapped, one install becomes an expensive
        # run on the installer's bill.
        with pytest.raises(UninstallableConfigError) as exc:
            sanitize_config({**_VALID, "system_instructions": "x" * (MAX_SYSTEM_INSTRUCTIONS + 1)})
        assert any("System instructions exceed" in problem for problem in exc.value.problems)

    def test_instructions_at_the_cap_are_accepted(self) -> None:
        config = sanitize_config({**_VALID, "system_instructions": "x" * MAX_SYSTEM_INSTRUCTIONS})
        assert len(config.system_instructions) == MAX_SYSTEM_INSTRUCTIONS

    def test_missing_instructions_default_to_empty_rather_than_failing(self) -> None:
        # A tools-only agent is a legitimate thing to publish.
        assert sanitize_config({"model": "gpt-4o-mini"}).system_instructions == ""

    def test_non_text_instructions_are_refused(self) -> None:
        with pytest.raises(UninstallableConfigError):
            sanitize_config({**_VALID, "system_instructions": ["a", "list"]})


class TestSamplingParameters:
    def test_temperature_outside_the_range_is_refused(self) -> None:
        for bad in (-0.1, 2.1, 100):
            with pytest.raises(UninstallableConfigError):
                sanitize_config({**_VALID, "temperature": bad})

    def test_the_range_boundaries_are_accepted(self) -> None:
        for good in (0, 2):
            assert sanitize_config({**_VALID, "temperature": good}).temperature == float(good)

    def test_a_boolean_temperature_is_refused_despite_being_an_int(self) -> None:
        # `isinstance(True, int)` is True in Python, so this needs an
        # explicit check or `temperature: true` silently becomes 1.0.
        with pytest.raises(UninstallableConfigError):
            sanitize_config({**_VALID, "temperature": True})

    def test_an_output_token_ceiling_is_enforced(self) -> None:
        # Without it a snapshot claiming ten million tokens installs
        # cleanly and fails at run time, in the installer's workspace.
        with pytest.raises(UninstallableConfigError):
            sanitize_config({**_VALID, "max_output_tokens": MAX_OUTPUT_TOKENS_CEILING + 1})

    def test_zero_output_tokens_is_refused(self) -> None:
        with pytest.raises(UninstallableConfigError):
            sanitize_config({**_VALID, "max_output_tokens": 0})

    def test_absent_sampling_parameters_stay_absent(self) -> None:
        # `None` means "use the platform default", which is a different
        # fact from any particular number.
        config = sanitize_config({"model": "gpt-4o-mini"})
        assert config.temperature is None
        assert config.max_output_tokens is None


class TestTools:
    def test_tools_are_carried_through(self) -> None:
        assert sanitize_config({**_VALID, "tools": ["web_search", "calculator"]}).tools == [
            "web_search",
            "calculator",
        ]

    def test_a_non_list_tools_value_is_refused(self) -> None:
        with pytest.raises(UninstallableConfigError):
            sanitize_config({**_VALID, "tools": "web_search"})

    def test_a_tool_that_is_not_a_name_is_refused(self) -> None:
        with pytest.raises(UninstallableConfigError):
            sanitize_config({**_VALID, "tools": ["web_search", {"exec": "rm -rf /"}]})

    def test_too_many_tools_are_refused(self) -> None:
        with pytest.raises(UninstallableConfigError):
            sanitize_config({**_VALID, "tools": [f"tool_{i}" for i in range(MAX_TOOLS + 1)]})


class TestProblemReporting:
    def test_every_problem_is_reported_at_once(self) -> None:
        # The installer is reporting someone else's broken listing. One
        # problem per attempt would make that impossible to describe.
        with pytest.raises(UninstallableConfigError) as exc:
            sanitize_config({"temperature": 9, "max_output_tokens": -1, "tools": "nope"})
        assert len(exc.value.problems) == 4


class TestUpgradeDetection:
    def test_a_newer_published_version_is_an_upgrade(self) -> None:
        assert is_upgrade(installed_version=1, latest_version=3) is True

    def test_the_same_version_is_not_an_upgrade(self) -> None:
        # Offering "update" for it would be a button that does nothing.
        assert is_upgrade(installed_version=3, latest_version=3) is False

    def test_an_older_latest_version_is_not_an_upgrade(self) -> None:
        # Reachable if a workspace pinned a version the publisher later
        # withdrew past. Not an upgrade, and not an error either.
        assert is_upgrade(installed_version=5, latest_version=3) is False
