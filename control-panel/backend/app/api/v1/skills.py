"""SkillHub skill 安装 API 路由。

鉴权：登录用户（含 admin）均可调用，只安装到 JWT 用户本人目录。
领域异常 → HTTP 映射仿照 thirdparty_agent.py（isinstance 表）；
注意错误 detail 用字符串（spec 016 §错误码），与 thirdparty_agent 的 {"message": ...} 刻意不同。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.iam.deps import Action, Resource, require_permission
from app.iam.tokens import TokenData
from app.schemas.litellm import ApiResponse
from app.schemas.skillhub import InstallSkillRequest, InstalledSkill
from app.services.skillhub_service import (
    ChecksumMismatchError,
    InvalidSkillPackageError,
    PackageTooLargeError,
    SkillExistsError,
    SkillNotFoundError,
    SkillhubConnectionError,
    SkillhubError,
    SkillhubNotConfiguredError,
    SkillhubService,
    SkillhubUpstreamError,
)

logger = logging.getLogger(__name__)

# 模块级单例（公开，供测试 monkeypatch 注入 mock，避免访问受保护成员 G.CLS.11）
svc = SkillhubService()

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])

# ── 领域异常 → HTTP 状态码 ──────────────────────────────────────────────

_EXCEPTION_STATUS: list[tuple[type[SkillhubError], int]] = [
    (SkillhubNotConfiguredError, 503),  # SKILLHUB_BASE_URL 为空
    (SkillhubConnectionError, 502),     # 连接失败 / 超时
    (SkillNotFoundError, 404),          # skill 不存在或不可下载
    (SkillExistsError, 409),            # 已存在且 force=false
    (ChecksumMismatchError, 400),       # 校验和不一致
    (InvalidSkillPackageError, 400),    # 缺 SKILL.md / zip-slip / 类型不支持
    (PackageTooLargeError, 400),        # 超 SKILLHUB_MAX_FILE_SIZE
]


def _to_http(exc: SkillhubError) -> HTTPException:
    """Convert domain exception to HTTPException via isinstance mapping."""
    if isinstance(exc, SkillhubUpstreamError):
        # spec 016：上游 404 → 404（skill 不存在/不可下载，如 zip 预签名链接失效），其余 → 502
        return HTTPException(
            status_code=404 if exc.status_code == 404 else 502,
            detail=str(exc),
        )
    status = 500
    for cls, code in _EXCEPTION_STATUS:
        if isinstance(exc, cls):
            status = code
            break
    return HTTPException(status_code=status, detail=str(exc))


# ── Routes ──────────────────────────────────────────────────────────────


@router.post("/install", response_model=ApiResponse[InstalledSkill])
async def install_skill(
    body: InstallSkillRequest,
    user: TokenData = Depends(require_permission(Resource.SKILLS, Action.WRITE)),
) -> ApiResponse[InstalledSkill]:
    """从 SkillHub 下载并安装公开 skill 到当前用户技能目录。"""
    try:
        result = await svc.install(
            username=user.username,
            skill_id=body.skill_id,
            version=body.version,
            force=body.force,
        )
    except SkillhubError as exc:
        logger.warning("skill install failed: %s", exc)
        raise _to_http(exc) from exc
    return ApiResponse(
        data=InstalledSkill(
            name=result.name,
            version=result.version,
            install_path=result.install_path,
            installed_at=result.installed_at,
        )
    )
