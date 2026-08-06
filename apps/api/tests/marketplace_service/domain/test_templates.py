"""The first-party template library, as data.

These check the library itself rather than any behaviour around it. A
curated set of twelve is small enough that a mistake in one is a
product defect people see on the front page, and most of these mistakes
are silent: a tool name nothing answers to, a slug that changed, a
description promising a capability the template cannot have.
"""

from __future__ import annotations

from agentverse_shared.agent_tools import BUILTIN_TOOL_NAMES

from agentverse_api.marketplace_service.domain.install import sanitize_config
from agentverse_api.marketplace_service.domain.templates import (
    PLATFORM_WORKSPACE_ID,
    TEMPLATES,
    AgentTemplate,
)


class TestTheLibrary:
    def test_there_are_twelve(self) -> None:
        assert len(TEMPLATES) == 12

    def test_slugs_are_unique(self) -> None:
        # A duplicate would collide on the listings unique index — in a
        # migration, in production.
        slugs = [template.slug for template in TEMPLATES]
        assert len(set(slugs)) == len(slugs)

    def test_slugs_are_url_safe(self) -> None:
        for template in TEMPLATES:
            assert template.slug == template.slug.lower()
            assert " " not in template.slug
            assert template.slug.replace("-", "").isalnum()

    def test_the_slugs_are_pinned(self) -> None:
        # A template's slug is its public URL and appears in people's
        # documentation. Changing one is a broken link, so it should
        # require deliberately editing this list.
        assert {template.slug for template in TEMPLATES} == {
            "research-assistant",
            "code-reviewer",
            "sql-analyst",
            "support-triage",
            "meeting-notes",
            "content-writer",
            "sales-qualifier",
            "onboarding-guide",
            "document-summarizer",
            "data-cleaner",
            "email-drafter",
            "process-automator",
        }

    def test_the_platform_workspace_id_is_a_fixed_uuid(self) -> None:
        # The seed migration and this module must agree on it without a
        # lookup.
        assert len(PLATFORM_WORKSPACE_ID) == 36
        assert PLATFORM_WORKSPACE_ID.count("-") == 4

    def test_categories_are_spread_across_the_catalog(self) -> None:
        # A library where eleven of twelve sit in one category makes the
        # category rail useless on the page it exists to serve.
        categories = {template.category_slug for template in TEMPLATES}
        assert len(categories) >= 6


class TestEveryTemplateIsInstallable:
    def test_every_config_survives_sanitisation(self) -> None:
        # The same gate a customer's listing passes through. A template
        # that fails it would be published and uninstallable.
        for template in TEMPLATES:
            sanitize_config(template.to_config())

    def test_every_named_tool_actually_exists(self) -> None:
        # The one that matters. The worker's resolver drops unknown tool
        # names silently, so a template naming `web_search` would install
        # cleanly and then run without it — while its own prompt tells
        # the model it has it.
        for template in TEMPLATES:
            assert set(template.tools) <= BUILTIN_TOOL_NAMES, template.slug

    def test_every_template_names_a_model(self) -> None:
        for template in TEMPLATES:
            assert template.model.strip()

    def test_temperatures_are_in_range(self) -> None:
        for template in TEMPLATES:
            if template.temperature is not None:
                assert 0.0 <= template.temperature <= 2.0, template.slug


class TestTemplateContent:
    def test_summaries_fit_a_catalog_card(self) -> None:
        # 280 is the API's own cap on `summary`; a template exceeding it
        # could not be edited through the same route a customer uses.
        for template in TEMPLATES:
            assert 20 <= len(template.summary) <= 280, template.slug

    def test_descriptions_meet_the_submission_bar(self) -> None:
        # Templates skip moderation, so nothing else enforces this — and
        # a first-party listing thinner than what we require of customers
        # would be the wrong way round.
        for template in TEMPLATES:
            assert len(template.description) >= 100, template.slug

    def test_system_instructions_are_substantial(self) -> None:
        # The prompt is the entire value of a template: the platform's
        # built-in tools are two functions, and knowledge bases and MCP
        # connections are workspace-scoped so a template cannot carry
        # them. A one-line prompt is not a template.
        for template in TEMPLATES:
            assert len(template.system_instructions) >= 200, template.slug

    def test_titles_are_distinct(self) -> None:
        titles = [template.title for template in TEMPLATES]
        assert len(set(titles)) == len(titles)


class TestConfigShape:
    def test_a_temperature_is_omitted_rather_than_nulled(self) -> None:
        # `None` and "absent" both mean "use the default", and carrying
        # an explicit null into the snapshot would make two encodings of
        # one fact.
        template = AgentTemplate(
            slug="t",
            title="T",
            category_slug="research",
            summary="s",
            description="d",
            model="gpt-4o-mini",
            system_instructions="i",
        )
        assert "temperature" not in template.to_config()

    def test_tools_are_copied_not_shared(self) -> None:
        # `to_config` handing out its own list would let an installer's
        # mutation reach the library.
        template = TEMPLATES[0]
        config = template.to_config()
        assert isinstance(config["tools"], list)
        assert config["tools"] is not template.tools
