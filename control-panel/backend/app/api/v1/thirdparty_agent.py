"""Agent Registry API routes — upload, build, build status.

All routes require admin role (``require_admin`` dependency).
Build progress is polled from image_process on status query (no callback).
"""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.iam.deps import require_admin
from app.iam.tokens import TokenData
from app.schemas.litellm import ApiResponse
from app.schemas.thirdparty_agent import (
    AgentInstallerUploadResult,
    BuildStatusResponse,
    BuildTaskRequest,
    BuildTaskResponse,
    InstallerListItem,
)

from app.thirdparty_agent.exceptions import ThirdpartyAgentError
from app.thirdparty_agent.package import PackageExtractError
from app.models.thirdparty_agent import ConcurrentBuildLimitError
from app.services.thirdparty_agent_service import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    InsufficientDiskSpaceError,
    ThirdpartyAgentService,
    PackageTooLargeError,
)

_svc = ThirdpartyAgentService()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/thirdparty_agent", tags=["thirdparty_agent"])

# ── 领域异常 → HTTP 状态码 ──────────────────────────────────────────────

_EXCEPTION_STATUS: list[tuple[type[ThirdpartyAgentError], int]] = [
    (PackageExtractError, 400),        # covers all subclasses via isinstance
    (PackageTooLargeError, 400),
    (ConcurrentBuildLimitError, 409),
    (AgentAlreadyExistsError, 409),
    (AgentNotFoundError, 404),
    (InsufficientDiskSpaceError, 507),
]


def _to_http(exc: ThirdpartyAgentError) -> HTTPException:
    """Convert domain exception to HTTPException via isinstance mapping."""
    status = 500
    for cls, code in _EXCEPTION_STATUS:
        if isinstance(exc, cls):
            status = code
            break
    return HTTPException(status_code=status, detail={"message": str(exc)})

# ── Routes ──────────────────────────────────────────────────────────────


@router.get("/installers", response_model=ApiResponse[list[InstallerListItem]])
async def installer_list(
    session: AsyncSession = Depends(get_async_session),
    _admin: TokenData = Depends(require_admin),
) -> ApiResponse[list[AgentInstallerUploadResult]]:
    """List all uploaded agent installers."""
    result = await _svc.list_installers(session)
    return ApiResponse(data=result)


@router.post("/installers", response_model=ApiResponse[AgentInstallerUploadResult])
async def installer_upload(
    package: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
    _admin: TokenData = Depends(require_admin),
) -> ApiResponse[AgentInstallerUploadResult]:
    """Upload an Agent offline package (.tgz)."""
    try:
        result = await _svc.upload(session, _admin.username, package)
    except ThirdpartyAgentError as e:
        logger.warning("upload failed: %s", e)
        raise _to_http(e) from e
    return ApiResponse(data=result)


@router.post("/build_tasks", response_model=ApiResponse[BuildTaskResponse])
async def build_task_create(
    body: BuildTaskRequest,
    session: AsyncSession = Depends(get_async_session),
    _admin: TokenData = Depends(require_admin),
) -> ApiResponse[BuildTaskResponse]:
    """Trigger an image build for an uploaded agent.

    Locates the installer by ``agent_name`` + ``version``, refreshes
    ``display_name`` and ``entrypoint``, then submits the build to image_process.
    """
    try:
        task = await _svc.create_build_task(
            session,
            body.agent_name,
            body.version,
            body.display_name,
            body.entrypoint,
        )
    except ThirdpartyAgentError as e:
        logger.warning("build failed: %s", e)
        raise _to_http(e) from e
    return ApiResponse(data=task)


@router.get("/build_tasks/{task_id}", response_model=ApiResponse[BuildStatusResponse])
async def build_task_status(
    task_id: str,
    session: AsyncSession = Depends(get_async_session),
    _admin: TokenData = Depends(require_admin),
) -> ApiResponse[BuildStatusResponse]:
    """Query build status; syncs from image_process while task is active."""
    result = await _svc.get_build_task(session, task_id)
    if result is None:
        logger.warning("build task not found: %s", task_id)
        raise HTTPException(
            status_code=404,
            detail={"message": f"build task not found: {task_id}"},
        )
    return ApiResponse(data=result)
