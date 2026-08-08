"""Hardware monitoring routes — multi-node nodes list and per-node snapshots."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.iam.deps import require_permission, Resource, Action
from app.iam.tokens import TokenData
from app.schemas.hardware import HardwareNodesData, NodeSnapshotData
from app.schemas.litellm import ApiResponse
from app.services.hardware_service import HardwareService

router = APIRouter(prefix="/api/v1/hardware", tags=["硬件监控"])

_require_hw_read = require_permission(Resource.HARDWARE, Action.READ)


def _get_hardware_service(request: Request) -> HardwareService:
    svc: HardwareService | None = getattr(request.app.state, "hardware_svc", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="硬件监控服务未就绪")
    return svc


@router.get(
    "/nodes",
    response_model=ApiResponse[HardwareNodesData],
    summary="硬件监控节点列表",
)
async def hardware_nodes(
    _user: TokenData = Depends(_require_hw_read),
    hw_svc: HardwareService = Depends(_get_hardware_service),
):
    return ApiResponse(data=await hw_svc.list_nodes())


@router.get(
    "/snapshot",
    response_model=ApiResponse[NodeSnapshotData],
    summary="单节点硬件实时快照",
)
async def hardware_snapshot(
    node: str = Query(..., description="节点 id，如 master 或 worker-1"),
    _user: TokenData = Depends(_require_hw_read),
    hw_svc: HardwareService = Depends(_get_hardware_service),
):
    from app.config import settings

    if node not in settings.allowed_node_ids:
        raise HTTPException(status_code=404, detail=f"未知节点: {node}")

    return ApiResponse(data=await hw_svc.get_node_snapshot(node))
