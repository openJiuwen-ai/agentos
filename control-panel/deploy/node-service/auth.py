"""JWT authentication for node-service.

Verifies the caller's token by calling back to control-panel's
``POST /api/v1/auth/verify`` endpoint.  The control-panel proxy
(``node_service.py``) forwards the original JWT in the Authorization
header; this module extracts it and validates remotely.

Uses only the Python standard library (urllib.request) — no extra
dependencies beyond FastAPI itself.

Usage in FastAPI routes::

    from fastapi import Depends
    from auth import require_admin

    @router.get("/some-endpoint")
    async def endpoint(_user=Depends(require_admin)):
        ...
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger("node-service.auth")

CONTROL_PANEL_URL = os.environ.get("CONTROL_PANEL_URL", "http://localhost:8090")
VERIFY_TIMEOUT = 5  # seconds

_bearer = HTTPBearer(auto_error=False)


@dataclass
class TokenData:
    user_id: str
    username: str
    role: str


def verify_token(token: str) -> TokenData:
    """Call control-panel POST /api/v1/auth/verify to validate the token."""
    url = f"{CONTROL_PANEL_URL.rstrip('/')}/api/v1/auth/verify"
    payload = json.dumps({
        "token": token,
        "resource_id": "node-service",
        "action_id": "manage",
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=VERIFY_TIMEOUT) as resp:
            body = json.loads(resp.read())
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, ConnectionRefusedError):
            raise HTTPException(
                status_code=502,
                detail=f"无法连接控制面板鉴权服务 ({CONTROL_PANEL_URL})，请检查服务是否运行",
            ) from e
        raise HTTPException(
            status_code=502,
            detail=f"控制面板鉴权请求失败 ({CONTROL_PANEL_URL}): {reason}",
        ) from e
    except TimeoutError as e:
        raise HTTPException(
            status_code=504,
            detail=f"控制面板鉴权超时 ({CONTROL_PANEL_URL}，超时 {VERIFY_TIMEOUT}s)",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"控制面板鉴权异常: {type(e).__name__}: {e}",
        ) from e

    data = body.get("data", {})

    if not data.get("valid"):
        raise HTTPException(
            status_code=401,
            detail="Token 无效或已过期，请重新登录",
        )

    if data.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail=f"需要管理员权限 (当前角色: {data.get('role', 'unknown')})",
        )

    return TokenData(
        user_id=data.get("user_id", ""),
        username=data.get("username", ""),
        role=data.get("role", ""),
    )


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> TokenData:
    """FastAPI dependency — validates JWT and ensures admin role.

    This is a sync function; FastAPI runs it in the threadpool so the
    blocking urllib call never stalls the event loop.

    Returns ``TokenData`` on success; raises 401/403/502 on failure.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="未提供认证凭据，请在 Authorization 头中携带 Bearer token")

    return verify_token(credentials.credentials)
