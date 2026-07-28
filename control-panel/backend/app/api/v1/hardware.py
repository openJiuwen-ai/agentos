"""Hardware monitoring route — returns real-time hardware snapshot."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from app.iam.deps import require_permission, Resource, Action
from app.iam.tokens import TokenData
from app.schemas.hardware import HardwareSnapshot
from app.schemas.litellm import ApiResponse
from app.services.hardware_monitor import HardwareMonitorService
from app.services.npu_monitor import NpuMonitor

router = APIRouter(prefix="/api/v1/hardware", tags=["硬件监控"])

_require_hw_read = require_permission(Resource.HARDWARE, Action.READ)


@router.get(
    "/snapshot",
    response_model=ApiResponse[HardwareSnapshot],
    summary="硬件实时快照",
)
async def hardware_snapshot(
    request: Request,
    _user: TokenData = Depends(_require_hw_read),
):
    hw_svc: HardwareMonitorService | None = getattr(request.app.state, "hardware_svc", None)
    npu_monitor: NpuMonitor | None = getattr(request.app.state, "npu_monitor", None)
    if hw_svc is None or npu_monitor is None:
        raise HTTPException(status_code=503, detail="硬件监控服务未就绪")

    snapshot, npus = await asyncio.gather(
        hw_svc.get_snapshot(),
        npu_monitor.get_npu_info(),
    )
    snapshot.npus = npus

    return ApiResponse(data=snapshot)
