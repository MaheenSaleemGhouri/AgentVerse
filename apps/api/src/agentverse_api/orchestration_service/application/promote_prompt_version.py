"""The gate: a `DRAFT` prompt version cannot become `ACTIVE` without a
passing eval run (docs/roadmap.md PHASE 8's named "CI-style gate").

`system_instructions`/`model` are immutable once `ACTIVE` (`domain.
prompt`'s own docstring) precisely so the eval run this gate checks
stays true of the version forever after — nothing about promotion
itself re-runs the harness; that already happened, and this function
only checks the recorded result.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_api.orchestration_service.domain.ports.prompt_repository import (
    EvalRunRepository,
    PromptVersionRepository,
)
from agentverse_api.orchestration_service.domain.prompt import (
    PromptVersion,
    PromptVersionNotFoundError,
    PromptVersionStatus,
    assert_transition,
)


class PromptVersionNotEvaluatedError(Exception):
    """No eval run has ever been recorded for this version. Maps to
    HTTP 422 — distinct from a failed eval (`PromptVersionFailedEvalError`)
    because the remediation differs: run the harness, versus fix the
    prompt and re-run it.
    """

    def __init__(self, version_id: str) -> None:
        self.version_id = version_id
        super().__init__(f"Prompt version {version_id!r} has never been evaluated")


class PromptVersionFailedEvalError(Exception):
    """The most recent eval run for this version did not pass. Maps to
    HTTP 422; the route surfaces the recorded run's per-example results
    so the caller sees *why*, per the acceptance criterion "the
    promotion is blocked with the failing eval results shown."
    """

    def __init__(self, version_id: str, eval_run_id: str) -> None:
        self.version_id = version_id
        self.eval_run_id = eval_run_id
        super().__init__(f"Prompt version {version_id!r}'s latest eval run did not pass")


@dataclass(slots=True)
class PromotePromptVersionResult:
    version: PromptVersion
    #: The template's previously-active version, now archived — `None`
    #: when this is the template's first-ever promotion. Returned so a
    #: caller can show "v2 replaced v1" rather than just "v2 is active".
    archived_version: PromptVersion | None


async def promote_prompt_version(
    *,
    version_id: str,
    versions: PromptVersionRepository,
    eval_runs: EvalRunRepository,
) -> PromotePromptVersionResult:
    version = await versions.get_by_id(version_id)
    if version is None:
        raise PromptVersionNotFoundError(version_id)

    assert_transition(current=version.status, target=PromptVersionStatus.ACTIVE)

    latest_run = await eval_runs.latest_for_version(version_id)
    if latest_run is None:
        raise PromptVersionNotEvaluatedError(version_id)
    if not latest_run.passed:
        raise PromptVersionFailedEvalError(version_id, latest_run.id)

    archived_version: PromptVersion | None = None
    previous_active = await versions.get_active(version.prompt_template_id)
    if previous_active is not None:
        assert_transition(current=previous_active.status, target=PromptVersionStatus.ARCHIVED)
        archived_version = await versions.set_status(
            version_id=previous_active.id, status=PromptVersionStatus.ARCHIVED
        )

    promoted = await versions.set_status(version_id=version_id, status=PromptVersionStatus.ACTIVE)
    return PromotePromptVersionResult(version=promoted, archived_version=archived_version)
