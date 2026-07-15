"""LitellmService FastAPI 依赖 — 从 app.state 获取单例。

Service 由 ``app.main`` 的 ``lifespan`` 创建并挂在 ``app.state.litellm_svc`` 上，
各路由通过 ``Depends(get_litellm_svc)`` 获取。

认证依赖已迁移至 ``app.iam.deps``（``get_current_user``、``require_admin``、
``require_permission``）。
"""

from fastapi import Request

from app.services.litellm_service import LitellmService


async def get_litellm_svc(request: Request) -> LitellmService:
    """FastAPI 依赖 — 从 app.state 获取 LitellmService 单例"""
    return request.app.state.litellm_svc
