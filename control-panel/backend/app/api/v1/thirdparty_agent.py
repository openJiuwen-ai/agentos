"""Agent Registry API routes — upload, build, build status.

All routes require admin role (``require_admin`` dependency).
"""

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
)
from app.services.thirdparty_agent_service import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    ThirdpartyAgentService,
    BuildTaskConflictError,
    InvalidPackageError,
    PackageTooLargeError,
)

_svc = ThirdpartyAgentService()

router = APIRouter(prefix="/api/v1/thirdparty_agent", tags=["thirdparty_agent"])

# ── 领域异常 → HTTP 状态码 ──────────────────────────────────────────────

_EXCEPTION_STATUS = {
    PackageTooLargeError: 400,
    InvalidPackageError: 400,
    AgentAlreadyExistsError: 409,
    AgentNotFoundError: 404,
    BuildTaskConflictError: 409,
}

# ── Routes ──────────────────────────────────────────────────────────────


@router.get("/installers", response_model=ApiResponse[list[AgentInstallerUploadResult]])
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
    except tuple(_EXCEPTION_STATUS) as e:
        raise HTTPException(
            status_code=_EXCEPTION_STATUS[type(e)],
            detail={"message": str(e)},
        ) from e
    return ApiResponse(data=result)


@router.post("/build_tasks", response_model=ApiResponse[BuildTaskResponse])
async def build_task_create(
    body: BuildTaskRequest,
    session: AsyncSession = Depends(get_async_session),
    _admin: TokenData = Depends(require_admin),
) -> ApiResponse[BuildTaskResponse]:
    """Trigger an image build for an uploaded agent.

    Locates the installer by ``agent_name`` + ``version``, refreshes
    ``display_name`` and ``entrypoint``, then creates the build task.
    """
    try:
        task = await _svc.create_build_task(
            session,
            body.agent_name,
            body.version,
            body.display_name,
            body.entrypoint,
        )
    except tuple(_EXCEPTION_STATUS) as e:
        raise HTTPException(
            status_code=_EXCEPTION_STATUS[type(e)],
            detail={"message": str(e)},
        ) from e
    return ApiResponse(data=task)


@router.get("/build_tasks/{task_id}", response_model=ApiResponse[BuildStatusResponse])
async def build_task_status(
    task_id: str,
    session: AsyncSession = Depends(get_async_session),
    _admin: TokenData = Depends(require_admin),
) -> ApiResponse[BuildStatusResponse]:
    """Query the build status and progress for a build task."""
    result = await _svc.get_build_task(session, task_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"build task not found: {task_id}"},
        )
    return ApiResponse(data=result)
