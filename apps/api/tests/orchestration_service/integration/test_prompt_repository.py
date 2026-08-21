"""Prompt versioning/eval harness against real Postgres (Phase 8).

These run as integration tests because two guarantees that matter are
database ones: the partial unique index enforcing at most one `active`
version per template (`ix ... one_active_per_template`), and the seed
migration (`6bcc98f697c2`) that grandfathered the 12 first-party
marketplace templates — a fake repository can be written to obey the
first and can't prove the second exists at all.
"""

from __future__ import annotations

import pytest
from agentverse_shared.cost_accounting import TokenUsage
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.orchestration_service.application.eval_harness.regression_runner import (
    RegressionRunner,
)
from agentverse_api.orchestration_service.application.promote_prompt_version import (
    PromptVersionFailedEvalError,
    promote_prompt_version,
)
from agentverse_api.orchestration_service.application.prompt_template_service import (
    PromptTemplateService,
)
from agentverse_api.orchestration_service.domain.entities import ChatResult
from agentverse_api.orchestration_service.domain.golden_dataset import RubricType
from agentverse_api.orchestration_service.domain.prompt import PromptVersionStatus
from agentverse_api.orchestration_service.infrastructure.prompt_repository import (
    SqlEvalRunRepository,
    SqlGoldenExampleRepository,
    SqlPromptTemplateRepository,
    SqlPromptVersionRepository,
)
from tests.fakes.provider_adapter import FakeProviderAdapter

pytestmark = pytest.mark.integration


def _service(session: AsyncSession) -> PromptTemplateService:
    return PromptTemplateService(
        templates=SqlPromptTemplateRepository(session),
        versions=SqlPromptVersionRepository(session),
        golden_examples=SqlGoldenExampleRepository(session),
    )


class TestSeededTemplateLibrary:
    """The grandfathering migration (`6bcc98f697c2`) actually ran."""

    async def test_the_support_triage_template_is_seeded_and_active(
        self, db_session: AsyncSession
    ) -> None:
        service = _service(db_session)
        active = await service.get_active_version("support-triage")
        assert active is not None
        assert active.status is PromptVersionStatus.ACTIVE
        assert active.version_number == 1
        assert "category:" in active.system_instructions

    async def test_every_first_party_template_has_at_least_one_golden_example(
        self, db_session: AsyncSession
    ) -> None:
        service = _service(db_session)
        templates = await service.list_templates()
        # 12 first-party templates seeded (`marketplace_service/domain/
        # templates.py`'s `TEMPLATES`), each grandfathered active.
        assert len(templates) == 12
        for template in templates:
            examples = await SqlGoldenExampleRepository(db_session).list_for_template(
                template.id
            )
            assert len(examples) >= 1, f"{template.slug!r} has no golden examples"

    async def test_no_fabricated_eval_run_was_seeded_for_the_grandfathered_versions(
        self, db_session: AsyncSession
    ) -> None:
        # This migration's own docstring: claiming an eval ran when none
        # did would be dishonest data. Confirmed structurally, not just
        # asserted in prose.
        service = _service(db_session)
        active = await service.get_active_version("support-triage")
        assert active is not None
        latest = await SqlEvalRunRepository(db_session).latest_for_version(active.id)
        assert latest is None


class TestFullLifecycleAgainstRealPostgres:
    """create -> draft -> golden example -> eval -> promote, real SQL
    repos end to end, provider faked (CLAUDE.md §11 — no real LLM call).
    """

    async def test_a_new_template_is_promoted_after_a_passing_eval(
        self, db_session: AsyncSession
    ) -> None:
        service = _service(db_session)
        template = await service.create_template(
            slug=f"test-template-{id(db_session)}",
            name="Test Template",
            description="A template created by an integration test.",
        )
        version = await service.create_draft_version(
            slug=template.slug,
            system_instructions="Respond with exactly: verdict: ok",
            model="gpt-4o-mini",
        )
        await service.add_golden_example(
            slug=template.slug,
            input={"prompt": "anything"},
            rubric=RubricType.SCHEMA,
            expectation={"required_labels": ["verdict"], "allowed_values": {"verdict": ["ok"]}},
        )

        runner = RegressionRunner(
            provider=FakeProviderAdapter(),  # default fake response: "fake response"
            versions=SqlPromptVersionRepository(db_session),
            golden_examples=SqlGoldenExampleRepository(db_session),
            eval_runs=SqlEvalRunRepository(db_session),
        )
        # The fake's default content ("fake response") has no
        # `verdict:` line, so this run genuinely fails the gate.
        run = await runner.run(prompt_version_id=version.id)
        assert run.passed is False

        eval_runs = SqlEvalRunRepository(db_session)
        with pytest.raises(PromptVersionFailedEvalError):
            await promote_prompt_version(
                version_id=version.id,
                versions=SqlPromptVersionRepository(db_session),
                eval_runs=eval_runs,
            )

        # Now a version whose eval genuinely passes.
        passing_result = ChatResult(
            content="verdict: ok",
            usage=TokenUsage(prompt_tokens=5, completion_tokens=5),
            finish_reason="stop",
        )
        passing_runner = RegressionRunner(
            provider=FakeProviderAdapter(chat_result=passing_result),
            versions=SqlPromptVersionRepository(db_session),
            golden_examples=SqlGoldenExampleRepository(db_session),
            eval_runs=SqlEvalRunRepository(db_session),
        )
        passing_run = await passing_runner.run(prompt_version_id=version.id)
        assert passing_run.passed is True

        result = await promote_prompt_version(
            version_id=version.id,
            versions=SqlPromptVersionRepository(db_session),
            eval_runs=SqlEvalRunRepository(db_session),
        )
        assert result.version.status is PromptVersionStatus.ACTIVE
        await db_session.rollback()


class TestOneActivePerTemplate:
    async def test_the_database_refuses_a_second_active_version_directly(
        self, db_session: AsyncSession
    ) -> None:
        # Proves the partial unique index, not just
        # `promote_prompt_version`'s application-layer check — a direct
        # UPDATE bypassing the gate must still be refused.
        service = _service(db_session)
        template = await service.create_template(
            slug=f"race-template-{id(db_session)}",
            name="Race Template",
            description="Proves the DB-level guarantee.",
        )
        v1 = await service.create_draft_version(
            slug=template.slug, system_instructions="v1", model="gpt-4o-mini"
        )
        v2 = await service.create_draft_version(
            slug=template.slug, system_instructions="v2", model="gpt-4o-mini"
        )
        await db_session.execute(
            text("UPDATE prompt_versions SET status = 'active' WHERE id = :id"), {"id": v1.id}
        )
        await db_session.flush()

        with pytest.raises(IntegrityError):
            await db_session.execute(
                text("UPDATE prompt_versions SET status = 'active' WHERE id = :id"),
                {"id": v2.id},
            )
            await db_session.flush()
        await db_session.rollback()
