"""seed prompt_templates/prompt_versions/golden examples from the first-party marketplace template library

Revision ID: 6bcc98f697c2
Revises: 91ca0b5e0f61
Create Date: 2026-08-21

Grandfathers AgentVerse's 12 existing first-party marketplace starter
templates (`marketplace_service/domain/templates.py`'s `TEMPLATES`)
into the prompt-versioning registry `91ca0b5e0f61` just created —
"data in a migration rather than a seed script" for the same reason
`d15a7c94b2e0` (the template library's own seed) gives: the registry
entry *is* the feature, and staging/production must never disagree on
what it contains.

**Why these versions are seeded `active`, not `draft`.** Every one of
these 12 prompts is already live in production, installed by real
workspaces, before this migration or `promote_prompt_version.py`'s
eval gate existed. Seeding them as `draft` (unable to serve until
someone manually promotes each one) would make this migration a
production incident, not a registry backfill — the same reasoning
`8c1d444558ec` grandfathered every pre-existing `api_keys` row to
`'user_api_key'` rather than leaving `kind` ambiguous. No fabricated
`prompt_eval_runs` row is inserted alongside them: claiming an eval
ran when none did would be dishonest data, not a backfill. The gate
applies going forward — the *next* version of any of these 12
templates cannot go active without a real, run eval.

**Why golden examples are seeded regardless.** Golden datasets are
structured data, not model output — writing them needs no LLM call and
carries no such honesty problem. Every example below is derived from
its template's own stated, distinguishing behavior (`support-triage`'s
literal `label:` output contract; the other eleven's specific promises —
"state your assumptions", "unknown is a real answer", "never invent a
fact" — each turned into a concrete, checkable input/expectation
pair), not padding for coverage's sake.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from agentverse_api.marketplace_service.domain.templates import TEMPLATES

revision: str = "6bcc98f697c2"
down_revision: str | None = "91ca0b5e0f61"
branch_labels: str | None = None
depends_on: str | None = None


def _template_id(slug: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"agentverse:prompt:template:{slug}"))


def _version_id(slug: str, version_number: int) -> str:
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"agentverse:prompt:version:{slug}:{version_number}")
    )


def _example_id(slug: str, index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"agentverse:prompt:golden:{slug}:{index}"))


# One or more (input, rubric, expectation) golden examples per template
# slug, each proving something the template's own system_instructions
# specifically promises — see this migration's module docstring.
_GOLDEN_EXAMPLES: dict[str, list[tuple[dict[str, object], str, dict[str, object]]]] = {
    "research-assistant": [
        (
            {
                "material": "The API rate limit is 100 requests per minute per API key.",
                "question": "What is the rate limit per API key?",
            },
            "keyword",
            {"must_contain": ["100 requests"]},
        )
    ],
    "code-reviewer": [
        (
            {"diff": "def divide(a, b):\n    return a / b"},
            "keyword",
            {"must_contain": ["zero"]},
        )
    ],
    "sql-analyst": [
        (
            {
                "question": "How many active users signed up last month?",
                "schema": "users(id, created_at, status)",
            },
            "keyword",
            {"must_contain": ["assum"]},
        )
    ],
    "support-triage": [
        (
            {
                "subject": "Charged twice",
                "body": (
                    "I'm being charged twice for my subscription this month, please refund "
                    "immediately, this is urgent, I run my business on this!"
                ),
            },
            "schema",
            {
                "required_labels": ["category", "severity", "confidence", "draft_reply"],
                "allowed_values": {"category": ["billing"], "severity": ["urgent", "high"]},
            },
        ),
        (
            {"subject": "Export to CSV", "body": "Is there a way to export my dashboard data to CSV?"},
            "schema",
            {
                "required_labels": ["category", "severity", "confidence", "draft_reply"],
                "allowed_values": {"category": ["how-to"], "severity": ["normal", "low"]},
            },
        ),
        (
            {"subject": "it's broken", "body": "nothing works"},
            "schema",
            {
                "required_labels": ["category", "severity", "confidence", "draft_reply"],
                "allowed_values": {"confidence": ["low"]},
            },
        ),
    ],
    "meeting-notes": [
        (
            {
                "transcript": (
                    "We decided to ship the export feature next sprint. Alex will own the "
                    "API side. We still need to figure out pricing for the enterprise tier."
                )
            },
            "keyword",
            {"must_contain": ["Decisions", "Actions", "Open"]},
        )
    ],
    "content-writer": [
        (
            {
                "facts": "We integrate with Slack and Notion. Free tier available.",
                "brief": "Write a one-line announcement for our new integrations.",
            },
            "keyword",
            {"must_contain": ["Slack", "Notion"], "must_not_contain": ["revolutionary"]},
        )
    ],
    "sales-qualifier": [
        (
            {
                "criteria": "Budget > $10k/year; Company size > 50 employees",
                "enquiry": "We're a 200-person company looking to switch tools next quarter.",
            },
            "keyword",
            {"must_contain": ["unknown"]},
        )
    ],
    "onboarding-guide": [
        (
            {
                "docs": "To reset your password, go to Settings > Security > Reset Password.",
                "question": "How do I change my password?",
            },
            "keyword",
            {"must_contain": ["Settings"]},
        )
    ],
    "document-summarizer": [
        (
            {
                "document": (
                    "Refunds are available within 30 days, except for digital downloads "
                    "which are non-refundable."
                )
            },
            "keyword",
            {"must_contain": ["except"]},
        )
    ],
    "data-cleaner": [
        (
            {"sample": "id,signup_date\n1,2026-01-05\n2,01/06/2026\n3,2026-01-07"},
            "keyword",
            {"must_contain": ["inconsist"]},
        )
    ],
    "email-drafter": [
        (
            {"thread": "Thanks for reaching out! What's your typical turnaround time?"},
            "keyword",
            {"must_contain": ["turnaround"], "must_not_contain": ["I confirm", "guarantee"]},
        )
    ],
    "process-automator": [
        (
            {"process": "When a customer submits a support ticket, an agent picks it up and responds."},
            "keyword",
            {"must_contain": ["timeout"]},
        )
    ],
}


def upgrade() -> None:
    templates_table = sa.table(
        "prompt_templates",
        sa.column("id", postgresql.UUID(as_uuid=False)),
        sa.column("slug", sa.Text),
        sa.column("name", sa.Text),
        sa.column("description", sa.Text),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    versions_table = sa.table(
        "prompt_versions",
        sa.column("id", postgresql.UUID(as_uuid=False)),
        sa.column("prompt_template_id", postgresql.UUID(as_uuid=False)),
        sa.column("version_number", sa.Integer),
        sa.column("system_instructions", sa.Text),
        sa.column("model", sa.Text),
        sa.column("temperature", sa.Float),
        sa.column("status", sa.Text),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("activated_at", sa.DateTime(timezone=True)),
    )
    examples_table = sa.table(
        "prompt_golden_examples",
        sa.column("id", postgresql.UUID(as_uuid=False)),
        sa.column("prompt_template_id", postgresql.UUID(as_uuid=False)),
        sa.column("input", postgresql.JSONB),
        sa.column("rubric", sa.Text),
        sa.column("expectation", postgresql.JSONB),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    for template in TEMPLATES:
        template_id = _template_id(template.slug)
        op.execute(
            templates_table.insert().values(
                id=template_id,
                slug=template.slug,
                name=template.title,
                description=template.summary,
                created_at=sa.func.now(),
                updated_at=sa.func.now(),
            )
        )
        op.execute(
            versions_table.insert().values(
                id=_version_id(template.slug, 1),
                prompt_template_id=template_id,
                version_number=1,
                system_instructions=template.system_instructions,
                model=template.model,
                temperature=template.temperature,
                status="active",
                created_at=sa.func.now(),
                activated_at=sa.func.now(),
            )
        )
        for index, (example_input, rubric, expectation) in enumerate(
            _GOLDEN_EXAMPLES.get(template.slug, [])
        ):
            op.execute(
                examples_table.insert().values(
                    id=_example_id(template.slug, index),
                    prompt_template_id=template_id,
                    input=example_input,
                    rubric=rubric,
                    expectation=expectation,
                    created_at=sa.func.now(),
                )
            )


def downgrade() -> None:
    # Typed `sa.table()` columns, not raw `sa.text()` with string
    # bindparams — a bare string parameter compared against a `uuid`
    # column fails with "operator does not exist: uuid = character
    # varying" (Postgres does not implicitly cast), the same class of
    # error `postgresql-expert` flags whenever a query mixes the two.
    template_ids = [_template_id(template.slug) for template in TEMPLATES]

    templates_table = sa.table(
        "prompt_templates", sa.column("id", postgresql.UUID(as_uuid=False))
    )
    versions_table = sa.table(
        "prompt_versions",
        sa.column("prompt_template_id", postgresql.UUID(as_uuid=False)),
    )
    examples_table = sa.table(
        "prompt_golden_examples",
        sa.column("prompt_template_id", postgresql.UUID(as_uuid=False)),
    )

    op.execute(
        examples_table.delete().where(examples_table.c.prompt_template_id.in_(template_ids))
    )
    op.execute(
        versions_table.delete().where(versions_table.c.prompt_template_id.in_(template_ids))
    )
    op.execute(templates_table.delete().where(templates_table.c.id.in_(template_ids)))
