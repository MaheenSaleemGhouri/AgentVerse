"""`/api/v1/admin/prompts` — prompt-versioning and the eval-harness gate
(Phase 8, docs/roadmap.md "PHASE 8"). Platform-staff only
(`require_platform_admin`): authoring a first-party prompt is a
platform-content decision, not a workspace action — the same authority
boundary `marketplace.py`'s `admin_router` already draws for moderating
listings.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.interface.dependencies.require_platform_admin import (
    require_platform_admin,
)
from agentverse_api.auth_service.interface.dependencies.services import get_audit_service
from agentverse_api.orchestration_service.application.eval_harness.regression_runner import (
    NoGoldenExamplesError,
    RegressionRunner,
)
from agentverse_api.orchestration_service.application.promote_prompt_version import (
    PromptVersionFailedEvalError,
    PromptVersionNotEvaluatedError,
    promote_prompt_version,
)
from agentverse_api.orchestration_service.application.prompt_template_service import (
    PromptTemplateNotFoundError,
    PromptTemplateService,
)
from agentverse_api.orchestration_service.domain.eval_run import EvalRun
from agentverse_api.orchestration_service.domain.ports.prompt_repository import EvalRunRepository
from agentverse_api.orchestration_service.domain.prompt import (
    InvalidPromptVersionTransitionError,
    PromptTemplate,
    PromptVersion,
    PromptVersionNotFoundError,
)
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_eval_run_repository,
    get_prompt_template_service,
    get_regression_runner,
)
from agentverse_api.orchestration_service.interface.schemas.prompts import (
    CreateDraftVersionRequest,
    EvalRunResponse,
    ExampleResultResponse,
    PromoteVersionResponse,
    PromptTemplateResponse,
    PromptVersionResponse,
)

router = APIRouter(prefix="/api/v1/admin/prompts", tags=["prompt-versioning"])


def _template_response(template: PromptTemplate) -> PromptTemplateResponse:
    return PromptTemplateResponse(
        id=template.id,
        slug=template.slug,
        name=template.name,
        description=template.description,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def _version_response(version: PromptVersion) -> PromptVersionResponse:
    return PromptVersionResponse(
        id=version.id,
        prompt_template_id=version.prompt_template_id,
        version_number=version.version_number,
        system_instructions=version.system_instructions,
        model=version.model,
        temperature=version.temperature,
        status=version.status.value,
        created_at=version.created_at,
        activated_at=version.activated_at,
    )


def _eval_run_response(run: EvalRun) -> EvalRunResponse:
    return EvalRunResponse(
        id=run.id,
        prompt_version_id=run.prompt_version_id,
        started_at=run.started_at,
        completed_at=run.completed_at,
        passed=run.passed,
        total_examples=run.total_examples,
        passed_examples=run.passed_examples,
        total_cost_micro_usd=run.total_cost_micro_usd,
        total_latency_ms=run.total_latency_ms,
        results=[
            ExampleResultResponse(
                golden_example_id=r.golden_example_id,
                passed=r.passed,
                reason=r.reason,
                cost_micro_usd=r.cost_micro_usd,
                latency_ms=r.latency_ms,
            )
            for r in run.results
        ],
    )


@router.get("", response_model=list[PromptTemplateResponse])
async def list_prompt_templates_route(
    _admin: str = Depends(require_platform_admin),
    service: PromptTemplateService = Depends(get_prompt_template_service),
) -> list[PromptTemplateResponse]:
    return [_template_response(t) for t in await service.list_templates()]


@router.get("/{slug}/versions", response_model=list[PromptVersionResponse])
async def list_prompt_versions_route(
    slug: str,
    _admin: str = Depends(require_platform_admin),
    service: PromptTemplateService = Depends(get_prompt_template_service),
) -> list[PromptVersionResponse]:
    try:
        versions = await service.list_versions(slug)
    except PromptTemplateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [_version_response(v) for v in versions]


@router.post(
    "/{slug}/versions", response_model=PromptVersionResponse, status_code=status.HTTP_201_CREATED
)
async def create_draft_version_route(
    slug: str,
    body: CreateDraftVersionRequest,
    admin_user_id: str = Depends(require_platform_admin),
    service: PromptTemplateService = Depends(get_prompt_template_service),
    audit: AuditService = Depends(get_audit_service),
) -> PromptVersionResponse:
    try:
        version = await service.create_draft_version(
            slug=slug,
            system_instructions=body.system_instructions,
            model=body.model,
            temperature=body.temperature,
        )
    except PromptTemplateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    await audit.record(
        action="prompt_version.drafted",
        outcome="success",
        workspace_id=None,
        actor_user_id=admin_user_id,
        target=version.id,
        metadata={"slug": slug, "version_number": str(version.version_number)},
    )
    return _version_response(version)


@router.post("/versions/{version_id}/eval-runs", response_model=EvalRunResponse)
async def run_eval_route(
    version_id: str,
    admin_user_id: str = Depends(require_platform_admin),
    runner: RegressionRunner = Depends(get_regression_runner),
    audit: AuditService = Depends(get_audit_service),
) -> EvalRunResponse:
    try:
        run = await runner.run(prompt_version_id=version_id)
    except PromptVersionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NoGoldenExamplesError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await audit.record(
        action="prompt_version.eval_run",
        outcome="success" if run.passed else "failed",
        workspace_id=None,
        actor_user_id=admin_user_id,
        target=version_id,
        metadata={
            "eval_run_id": run.id,
            "passed_examples": str(run.passed_examples),
            "total_examples": str(run.total_examples),
        },
    )
    return _eval_run_response(run)


@router.post("/versions/{version_id}/promote", response_model=PromoteVersionResponse)
async def promote_version_route(
    version_id: str,
    admin_user_id: str = Depends(require_platform_admin),
    service: PromptTemplateService = Depends(get_prompt_template_service),
    eval_runs: EvalRunRepository = Depends(get_eval_run_repository),
    audit: AuditService = Depends(get_audit_service),
) -> PromoteVersionResponse:
    """The gate: blocked with the failing eval results shown (422,
    carrying the eval run id a caller can fetch) rather than a bare
    refusal — the acceptance criterion's literal wording.
    """
    try:
        result = await promote_prompt_version(
            version_id=version_id, versions=service.versions, eval_runs=eval_runs
        )
    except PromptVersionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidPromptVersionTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PromptVersionNotEvaluatedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "not_evaluated", "message": str(exc)},
        ) from exc
    except PromptVersionFailedEvalError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "eval_failed",
                "message": str(exc),
                "eval_run_id": exc.eval_run_id,
            },
        ) from exc

    await audit.record(
        action="prompt_version.promoted",
        outcome="success",
        workspace_id=None,
        actor_user_id=admin_user_id,
        target=version_id,
        metadata={
            "archived_version_id": (
                result.archived_version.id if result.archived_version is not None else ""
            )
        },
    )
    return PromoteVersionResponse(
        version=_version_response(result.version),
        archived_version=(
            _version_response(result.archived_version)
            if result.archived_version is not None
            else None
        ),
    )
