"""User management API routes: batch create, list, me, password, edit, delete.

Thin orchestration layer — delegates to ``AbstractUserBackend`` for all
user CRUD and to ``iam.deps`` for auth dependencies.  Backend-agnostic.
"""

import uuid
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query

from app.iam.deps import get_current_user, get_user_backend, require_admin, TokenData
from app.schemas.user import (
    BatchCreateRequest,
    ChangePasswordRequest,
    UpdateUserRequest,
)
from app.services.base import AbstractUserBackend

router = APIRouter(prefix="/api/v1/users", tags=["users"])


# ── Query parameter bundles ──────────────────────────────────────────────


@dataclass
class _ListUsersQuery:
    """Bundle list_users query params to keep the function signature lean."""

    page: int = Query(1, ge=1)
    page_size: int = Query(20, ge=1, le=100)
    sort: str = Query("created_at")
    order: str = Query("desc")
    search: str | None = Query(None)


# ── Admin routes ────────────────────────────────────────────────────────

@router.post("/batch")
async def batch_create(
    body: BatchCreateRequest,
    backend: AbstractUserBackend = Depends(get_user_backend),
    _admin: TokenData = Depends(require_admin),
):
    """Admin: batch create users with auto-generated passwords."""
    results = []
    for username in body.usernames:
        try:
            record, password = await backend.create_user(username)
            results.append({
                "username": record.username,
                "user_id": record.user_id,
                "password": password,
                "error": None,
            })
        except ValueError as e:
            results.append({
                "username": username.strip().lower(),
                "user_id": None, "password": None, "error": str(e),
            })
    return {"code": 201, "message": "success", "data": results}


@router.get("")
async def list_users(
    q: _ListUsersQuery = Depends(),
    backend: AbstractUserBackend = Depends(get_user_backend),
    _admin: TokenData = Depends(require_admin),
):
    """Admin: paginated user list with optional username search."""
    result = await backend.list_users(q.page, q.page_size, q.sort, q.order, q.search)
    items = [
        {
            "user_id": u.user_id, "username": u.username,
            "role": u.role, "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in result.items
    ]
    return {"code": 200, "data": {"total": result.total, "items": items}}


@router.patch("/{user_id}")
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    backend: AbstractUserBackend = Depends(get_user_backend),
    _admin: TokenData = Depends(require_admin),
):
    """Admin: update user role or active status."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="无效的 user_id") from e

    target = await backend.get_user_by_id(uid)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.role == "admin":
        raise HTTPException(status_code=403, detail="不能修改管理员账户")

    update_dict = {}
    if body.is_active is not None:
        update_dict["is_active"] = body.is_active

    try:
        user = await backend.update_user(uid, update_dict)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return {
        "code": 200,
        "data": {
            "user_id": user.user_id, "username": user.username,
            "role": user.role, "is_active": user.is_active,
        },
    }


@router.delete("/{user_id}")
async def delete_user_endpoint(
    user_id: str,
    backend: AbstractUserBackend = Depends(get_user_backend),
    current_user: TokenData = Depends(require_admin),
):
    """Admin: delete user and their home directory."""
    if user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="不能删除自己")

    try:
        uid = uuid.UUID(user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="无效的 user_id") from e

    target = await backend.get_user_by_id(uid)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.role == "admin":
        raise HTTPException(status_code=403, detail="不能删除管理员账户")

    try:
        await backend.delete_user(uid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return {"code": 200, "message": "用户已删除", "data": None}


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    backend: AbstractUserBackend = Depends(get_user_backend),
    _admin: TokenData = Depends(require_admin),
):
    """Admin: reset a user's password to a random one."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="无效的 user_id") from e

    try:
        user = await backend.get_user_by_id(uid)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        if user.role == "admin":
            raise HTTPException(status_code=403, detail="不能重置管理员密码")
        new_password = await backend.reset_password(uid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return {"code": 200, "data": {"user_id": user_id, "username": user.username, "new_password": new_password}}


# ── Self-service routes ─────────────────────────────────────────────────

@router.get("/me")
async def get_me(
    user: TokenData = Depends(get_current_user),
    backend: AbstractUserBackend = Depends(get_user_backend),
):
    """Current user profile."""
    try:
        uid = uuid.UUID(user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail="Token 无效") from e

    u = await backend.get_user_by_id(uid)
    if not u:
        raise HTTPException(status_code=401, detail="用户不存在")

    return {
        "code": 200,
        "data": {
            "user_id": u.user_id, "username": u.username,
            "role": u.role, "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        },
    }


@router.put("/me/password")
async def change_my_password(
    body: ChangePasswordRequest,
    user: TokenData = Depends(get_current_user),
    backend: AbstractUserBackend = Depends(get_user_backend),
):
    """Change own password.  Invalidates all existing refresh tokens."""
    try:
        uid = uuid.UUID(user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail="Token 无效") from e

    try:
        await backend.change_password(uid, body.old_password, body.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {"code": 200, "message": "密码修改成功", "data": None}
