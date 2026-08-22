"""OAuth2 Provider endpoints — authorize, token, userinfo.

薄路由层：只做参数提取、跳转 URL 拼接与错误转换，业务逻辑在
``app.services.oauth_service`` 的 ``OAuth2Service`` 类下，数据库操作
封装在 ``app.models.oauth2_auth_code`` 类方法中。

端点总览（RFC 6749 授权码模式）：
- GET  /api/v1/oauth2/authorize  — authorization endpoint（浏览器入口）
- POST /api/v1/oauth2/authorize  — 同意/拒绝决策（CP 前端内部调用，非规范端点）
- POST /api/v1/oauth2/token      — token endpoint（server-to-server）
- GET  /api/v1/oauth2/userinfo   — token 校验端点（server-to-server，非规范端点）
"""

from __future__ import annotations

from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.config import settings
from app.iam.deps import (
    TokenData,
    get_current_oauth_user,
    get_current_user,
)
from app.services.oauth_service import (
    OAuth2Error,
    OAuth2Service,
)

# /api/v1/oauth2/* 路由（浏览器重定向 + 前端决策 + server-to-server 调用）
oauth2_router = APIRouter(prefix="/api/v1/oauth2", tags=["oauth2"])


# ── GET /api/v1/oauth2/authorize ──────────────────────────────────────
# RFC 6749 §3.1 authorization endpoint — OAuth 流程的浏览器入口。
# SkillHub 将用户浏览器重定向到此，本端点负责：
#   1. 服务端安全闸门：校验 client_id / redirect_uri，非法请求连登录页都看不到
#      （client_id 未知 → 拒绝；redirect_uri 不匹配 → 防开放重定向攻击）
#   2. 参数搬运：把规范参数转发给 Vue 前端 /oauth/authorize（零 Cookie 设计，
#      参数走 URL query string）
# 登录与同意 UI 由前端完成，本端点不渲染任何页面。


@oauth2_router.get("/authorize")
async def oauth2_authorize(
    client_id: str,
    redirect_uri: str,
    state: str | None = None,
):
    """授权入口：校验 client_id / redirect_uri → 302 跳转前端 /oauth/authorize。

    参数与 RFC 6749 §4.1.1 一致；state 由客户端生成（防 CSRF），此处原样透传。
    """
    try:
        OAuth2Service.validate_authorize_params(client_id, redirect_uri)
    except OAuth2Error as exc:
        return _redirect_error(exc.error)

    # client_name 由后端配置注入（环境变量 OAUTH2_CLIENT_NAME），
    # 透传给前端登录/同意页展示，避免在前端硬编码客户端名称。
    # 启动期 _OAUTH2_ENABLED 已保证 OAUTH2_CLIENT_NAME 非空，此处直接使用。
    query: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state or "",
        "client_name": settings.OAUTH2_CLIENT_NAME,
    }
    qs = urlencode(query, quote_via=quote)
    return RedirectResponse(
        url=f"{settings.OAUTH2_FRONTEND_ORIGIN}/oauth/authorize?{qs}",
        status_code=302,
    )


# ── POST /api/v1/oauth2/authorize ───────────────────────────────────
# CP 前端内部端点（非 RFC 6749 规范端点）— 用户在同意页点击"允许/拒绝"后调用。
# 身份来源：CP 登录 JWT（Authorization: Bearer 头），而非 OAuth2 参数。
# OAuth 参数由前端回传（来自 URL query），此处再次校验以防篡改。


class OAuthDecision(BaseModel):
    """前端同意页提交的决策。"""

    action: str  # "allow" or "deny"
    client_id: str
    redirect_uri: str
    state: str = ""


@oauth2_router.post("/authorize")
async def oauth2_authorize_decision(
    body: OAuthDecision,
    token_data: TokenData = Depends(get_current_user),
):
    """处理用户的同意/拒绝决定，返回前端应跳转的 redirect_uri（含 code 或 error）。

    allow → 生成授权码（256 位随机，一次性，10 分钟过期）→ "{redirect_uri}?code=...&state=..."
    deny  → "{redirect_uri}?error=access_denied&state=..."
    """
    # 再次校验 OAuth 参数（前端回传的，防止篡改）
    try:
        OAuth2Service.validate_authorize_params(body.client_id, body.redirect_uri)
    except OAuth2Error as exc:
        raise HTTPException(status_code=exc.status_code, detail={"error": exc.error}) from exc

    if body.action == "deny":
        qs = urlencode({"error": "access_denied", "state": body.state})
        return {"redirect_uri": f"{body.redirect_uri}?{qs}"}

    if body.action != "allow":
        raise HTTPException(status_code=400, detail={"error": "action must be 'allow' or 'deny'"})

    code = await OAuth2Service.create_authorization_code(
        user_id=token_data.user_id,
        client_id=body.client_id,
        redirect_uri=body.redirect_uri,
    )
    qs = urlencode({"code": code, "state": body.state}, quote_via=quote)
    return {"redirect_uri": f"{body.redirect_uri}?{qs}"}


# ── POST /api/v1/oauth2/token ────────────────────────────────────────
# RFC 6749 §3.2 token endpoint — SkillHub 后端用授权码换取 access_token。
# server-to-server 调用，浏览器不直接访问。
# 参数规范要求 application/x-www-form-urlencoded（Form(...) 声明）。
# client_secret 常量时间比较（防时序攻击）；授权码原子消费（防重放）。


@oauth2_router.post("/token")
async def oauth2_token(
    grant_type: str = Form(...),
    code: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
):
    """授权码换 JWT access_token（type: "oauth2_access"，与登录 JWT 类型隔离）。

    业务逻辑（grant_type 校验、client 凭据校验、授权码消费与过期检查、
    JWT 签发）在 ``OAuth2Service.exchange_code_for_token`` 中。
    """
    try:
        return await OAuth2Service.exchange_code_for_token(
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            grant_type=grant_type,
        )
    except OAuth2Error as exc:
        raise HTTPException(status_code=exc.status_code, detail={"error": exc.error}) from exc


# ── GET /api/v1/oauth2/userinfo ──────────────────────────────────────
# 非 RFC 6749 规范端点（规范未定义 userinfo，那是 OIDC 的）— SkillHub 的
# 需求定制：SkillHub 每次 API 调用都用 Bearer token 请求此端点校验身份，
# 因为 SkillHub 无本地用户表，本端点是唯一的用户状态来源。


@oauth2_router.get("/userinfo")
async def oauth2_userinfo(
    userinfo: dict = Depends(get_current_oauth_user),
):
    """Bearer JWT → 用户身份 {id, username, login, name}。

    校验链：JWT 签名 + 过期 → type 必须为 oauth2_access（拒绝登录 JWT）→
    查库确认用户存在且 is_active（禁用的用户 token 立即失效）。
    逻辑封装在 ``app.iam.security.get_current_oauth_user``。
    """
    return userinfo


# ── Helpers ────────────────────────────────────────────────────────────


def _redirect_error(message: str) -> RedirectResponse:
    """授权入口校验失败时 302 跳转到前端 /oauth/error。"""
    err_params = urlencode({"oauth_error": message}, quote_via=quote)
    return RedirectResponse(
        url=f"{settings.OAUTH2_FRONTEND_ORIGIN}/oauth/error?{err_params}",
        status_code=302,
    )
