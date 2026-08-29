"""Third-party agent card APIs."""

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.iam.deps import get_current_user, require_admin
from app.iam.tokens import TokenData
from app.schemas.litellm import ApiResponse
from app.schemas.thirdparty_agent import (
    CardDetail,
    CardListQuery,
    CardListResponse,
    PublishAccepted,
    SetDefaultRequest,
    UnregisteredListResponse,
    UnregisteredStatus,
)
from app.services.thirdparty_agent_service import PublishParams, ThirdpartyAgentService
from app.thirdparty_agent.exceptions import (
    AgentNotFoundError,
    AgentServiceError,
    CardHasInstancesError,
    DefaultVersionProtectedError,
    InsufficientDiskSpaceError,
    InvalidUploadError,
    PackageLockedError,
    PackageTooLargeError,
    ThirdpartyAgentError,
)

_svc = ThirdpartyAgentService()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/thirdparty_agent", tags=["thirdparty_agent"])

_EXCEPTION_STATUS: list[tuple[type[ThirdpartyAgentError], int]] = [
    (InvalidUploadError, 400),
    (PackageTooLargeError, 400),
    (PackageLockedError, 409),
    (CardHasInstancesError, 409),
    (DefaultVersionProtectedError, 409),
    (AgentNotFoundError, 404),
    (InsufficientDiskSpaceError, 507),
    (AgentServiceError, 502),
]


def _to_http(exc: ThirdpartyAgentError) -> HTTPException:
    status = 500
    for cls, code in _EXCEPTION_STATUS:
        if isinstance(exc, cls):
            status = code
            break
    return HTTPException(status_code=status, detail={"message": str(exc)})


@router.post("/cards", response_model=ApiResponse[PublishAccepted], status_code=202)
async def publish_card(
    package: UploadFile = File(...),
    launch_command: str = Form(..., min_length=1, max_length=512),
    session: AsyncSession = Depends(get_async_session),
    _admin: TokenData = Depends(require_admin),
) -> ApiResponse[PublishAccepted]:
    try:
        result = await _svc.publish(
            session,
            package,
            PublishParams(
                uploaded_by=_admin.username,
                launch_command=launch_command,
            ),
        )
    except ThirdpartyAgentError as e:
        raise _to_http(e) from e
    return ApiResponse(data=result)


@router.get("/cards", response_model=ApiResponse[CardListResponse])
async def list_cards(
    query: CardListQuery = Depends(),
    session: AsyncSession = Depends(get_async_session),
    user: TokenData = Depends(get_current_user),
) -> ApiResponse[CardListResponse]:
    try:
        result = await _svc.list_cards(
            session,
            is_admin=user.role == "admin",
            framework=query.framework,
            page=query.page,
            size=query.size,
        )
    except ThirdpartyAgentError as e:
        raise _to_http(e) from e
    return ApiResponse(data=result)


@router.get("/cards/{framework}/{version}", response_model=ApiResponse[CardDetail])
async def get_card(
    framework: str,
    version: str,
    session: AsyncSession = Depends(get_async_session),
    user: TokenData = Depends(get_current_user),
) -> ApiResponse[CardDetail]:
    try:
        result = await _svc.get_card(
            session,
            is_admin=user.role == "admin",
            framework=framework,
            version=version,
        )
    except ThirdpartyAgentError as e:
        raise _to_http(e) from e
    return ApiResponse(data=result)


@router.put("/cards/{framework}/default", response_model=ApiResponse[dict])
async def set_default_version(
    framework: str,
    body: SetDefaultRequest,
    _admin: TokenData = Depends(require_admin),
) -> ApiResponse[dict]:
    try:
        await _svc.set_default_version(framework, body.framework_version)
    except ThirdpartyAgentError as e:
        raise _to_http(e) from e
    return ApiResponse(data={"status": "updated", "default": body.framework_version})


@router.delete("/cards/{framework}/{version}", response_model=ApiResponse[dict])
async def delete_card(
    framework: str,
    version: str,
    session: AsyncSession = Depends(get_async_session),
    _admin: TokenData = Depends(require_admin),
) -> ApiResponse[dict]:
    try:
        await _svc.delete_card(session, framework, version)
    except ThirdpartyAgentError as e:
        raise _to_http(e) from e
    return ApiResponse(data={"status": "deleted"})


@router.get("/unregistered", response_model=ApiResponse[UnregisteredListResponse])
async def list_unregistered(
    session: AsyncSession = Depends(get_async_session),
    _admin: TokenData = Depends(require_admin),
) -> ApiResponse[UnregisteredListResponse]:
    result = await _svc.list_unregistered(session)
    return ApiResponse(data=result)


@router.get("/unregistered/{digest}", response_model=ApiResponse[UnregisteredStatus])
async def get_unregistered(
    digest: str,
    session: AsyncSession = Depends(get_async_session),
    _admin: TokenData = Depends(require_admin),
) -> ApiResponse[UnregisteredStatus]:
    try:
        result = await _svc.get_unregistered(session, digest)
    except ThirdpartyAgentError as e:
        raise _to_http(e) from e
    return ApiResponse(data=result)


@router.post(
    "/unregistered/{digest}/retry",
    response_model=ApiResponse[PublishAccepted],
    status_code=202,
)
async def retry_unregistered(
    digest: str,
    launch_command: str = Form(..., min_length=1, max_length=512),
    session: AsyncSession = Depends(get_async_session),
    admin: TokenData = Depends(require_admin),
) -> ApiResponse[PublishAccepted]:
    try:
        result = await _svc.retry(session, digest, launch_command, admin.username)
    except ThirdpartyAgentError as e:
        raise _to_http(e) from e
    return ApiResponse(data=result)


@router.delete("/unregistered/{digest}", response_model=ApiResponse[dict])
async def delete_unregistered(
    digest: str,
    session: AsyncSession = Depends(get_async_session),
    _admin: TokenData = Depends(require_admin),
) -> ApiResponse[dict]:
    try:
        await _svc.delete_unregistered(session, digest)
    except ThirdpartyAgentError as e:
        raise _to_http(e) from e
    return ApiResponse(data={"status": "deleted"})
