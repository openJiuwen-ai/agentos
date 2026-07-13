"""IAM auth + user management API 集成测试。

使用 conftest.py 的 client + admin_tokens fixture（内存 SQLite + local_users backend）。
覆盖：登录/刷新/登出/权限校验/用户 CRUD/密码管理/home 目录。
"""

import pytest


# ── Auth: Login ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_success(client, test_data):
    """正确的用户名+密码 → 返回 access_token, refresh_token, user_id, username, role。"""
    admin = test_data["admin"]
    resp = await client.post("/api/v1/auth/login", json={
        "username": admin["username"], "password": admin["password"],
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["user_id"]
    assert data["username"] == admin["username"]
    assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_login_wrong_password(client, test_data):
    """错误密码 → 401。"""
    resp = await client.post("/api/v1/auth/login", json={
        "username": test_data["admin"]["username"],
        "password": test_data["passwords"]["wrong"],
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client, test_data):
    """不存在的用户 → 401（不泄露用户是否存在）。"""
    nu = test_data["nonexistent_user"]
    resp = await client.post("/api/v1/auth/login", json={
        "username": nu["username"], "password": nu["password"],
    })
    assert resp.status_code == 401


# ── Auth: Refresh ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refresh_success(client, admin_tokens):
    """有效的 refresh_token → 返回新 token 对。"""
    resp = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": admin_tokens["refresh_token"],
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["user_id"] == admin_tokens["user_id"]
    assert data["username"] == "admin"


@pytest.mark.asyncio
async def test_refresh_revoked(client, admin_tokens):
    """登出后再用 refresh_token → 401（token 已被吊销）。"""
    # 登出
    await client.post("/api/v1/auth/logout", json={
        "refresh_token": admin_tokens["refresh_token"],
    }, headers={"Authorization": f"Bearer {admin_tokens['access_token']}"})

    # 刷新应失败
    resp = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": admin_tokens["refresh_token"],
    })
    assert resp.status_code == 401


# ── Auth: Verify ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_admin_full_access(client, admin_tokens):
    """admin 对所有资源+操作有完全访问权限。"""
    resp = await client.post("/api/v1/auth/verify", json={
        "token": admin_tokens["access_token"],
        "resource_id": "inference.models",
        "action_id": "write",
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["valid"] is True
    assert data["authorized"] is True
    assert data["user_id"]


@pytest.mark.asyncio
async def test_verify_invalid_token(client):
    """无效 token → valid=false。"""
    resp = await client.post("/api/v1/auth/verify", json={
        "token": "not.a.real.token",
        "resource_id": "dashboard",
        "action_id": "read",
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["valid"] is False


# ── Auth: Permissions ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_permissions_admin(client, admin_tokens):
    """admin 获得完整权限矩阵（read/write/delete/manage）。"""
    resp = await client.get("/api/v1/auth/permissions", headers={
        "Authorization": f"Bearer {admin_tokens['access_token']}",
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["role"] == "admin"
    assert data["user_id"]
    assert data["username"] == "admin"
    assert data["permissions"]["inference.models"] == ["read", "write", "delete", "manage"]


# ── Auth: Middleware ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_token_401(client):
    """无 token 访问受保护端点 → 401。"""
    resp = await client.get("/api/v1/users")
    assert resp.status_code == 401


# ── Users: Batch Create ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_batch_create_users(client, admin_tokens):
    """admin 批量创建用户 → 返回 user_id + 自动生成密码 + 可用密码登录。"""
    resp = await client.post("/api/v1/users/batch", json={
        "usernames": ["alice", "bob", "charlie"],
    }, headers={"Authorization": f"Bearer {admin_tokens['access_token']}"})
    assert resp.status_code == 200
    users = resp.json()["data"]  # 官方 API: data 直接是列表
    assert len(users) == 3
    for u in users:
        assert u["user_id"] is not None
        assert u["password"] is not None
        assert u["error"] is None
        # 每个用户应能登录
        login_resp = await client.post("/api/v1/auth/login", json={
            "username": u["username"], "password": u["password"],
        })
        assert login_resp.status_code == 200
        assert login_resp.json()["data"]["role"] == "user"


@pytest.mark.asyncio
async def test_batch_create_duplicate(client, admin_tokens):
    """重复用户名 → 返回 error，其他用户正常创建。"""
    resp = await client.post("/api/v1/users/batch", json={
        "usernames": ["dave", "dave", "eve"],
    }, headers={"Authorization": f"Bearer {admin_tokens['access_token']}"})
    assert resp.status_code == 200
    users = resp.json()["data"]
    assert len(users) == 3
    assert users[0]["error"] is None       # 第一个 "dave" — 成功
    assert users[1]["error"] is not None   # 第二个 "dave" — 重复
    assert users[2]["error"] is None       # "eve" — 成功


@pytest.mark.asyncio
async def test_batch_create_requires_admin(client, admin_tokens):
    """非 admin 批量创建 → 403。"""
    # 先创建一个普通用户
    resp = await client.post("/api/v1/users/batch", json={
        "usernames": ["frank"],
    }, headers={"Authorization": f"Bearer {admin_tokens['access_token']}"})
    frank_pw = resp.json()["data"][0]["password"]

    # 以 frank 身份登录
    login_resp = await client.post("/api/v1/auth/login", json={
        "username": "frank", "password": frank_pw,
    })
    frank_token = login_resp.json()["data"]["access_token"]

    # 以 frank 身份批量创建 → 403
    resp = await client.post("/api/v1/users/batch", json={
        "usernames": ["grace"],
    }, headers={"Authorization": f"Bearer {frank_token}"})
    assert resp.status_code == 403


# ── Users: List ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_users(client, admin_tokens):
    """admin 列出所有用户。"""
    resp = await client.get("/api/v1/users", headers={
        "Authorization": f"Bearer {admin_tokens['access_token']}",
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 1
    assert any(u["username"] == "admin" for u in data["items"])


# ── Users: Me ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_me(client, admin_tokens):
    """获取当前用户信息。"""
    resp = await client.get("/api/v1/users/me", headers={
        "Authorization": f"Bearer {admin_tokens['access_token']}",
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["username"] == "admin"
    assert data["role"] == "admin"
    assert data["user_id"] == admin_tokens["user_id"]


# ── Users: Change Password ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_change_password(client, admin_tokens, test_data):
    """修改密码 → 旧 refresh_token 失效，新密码可登录。"""
    admin = test_data["admin"]
    new_pw = test_data["passwords"]["new"]
    resp = await client.put("/api/v1/users/me/password", json={
        "old_password": admin["password"],
        "new_password": new_pw,
    }, headers={"Authorization": f"Bearer {admin_tokens['access_token']}"})
    assert resp.status_code == 200

    # 旧 refresh_token 应失效（token_version 已 bump）
    refresh_resp = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": admin_tokens["refresh_token"],
    })
    assert refresh_resp.status_code == 401

    # 新密码可以登录
    login_resp = await client.post("/api/v1/auth/login", json={
        "username": admin["username"], "password": new_pw,
    })
    assert login_resp.status_code == 200

    # 改回原密码，避免影响其他测试
    new_tokens = login_resp.json()["data"]
    await client.put("/api/v1/users/me/password", json={
        "old_password": new_pw,
        "new_password": admin["password"],
    }, headers={"Authorization": f"Bearer {new_tokens['access_token']}"})


@pytest.mark.asyncio
async def test_change_password_wrong_old(client, admin_tokens, test_data):
    """旧密码错误 → 400。"""
    resp = await client.put("/api/v1/users/me/password", json={
        "old_password": test_data["passwords"]["wrong"],
        "new_password": test_data["passwords"]["new"],
    }, headers={"Authorization": f"Bearer {admin_tokens['access_token']}"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_change_password_too_short(client, admin_tokens, test_data):
    """新密码不足 8 位 → 422（Pydantic 校验）。"""
    resp = await client.put("/api/v1/users/me/password", json={
        "old_password": test_data["admin"]["password"],
        "new_password": test_data["passwords"]["too_short"],
    }, headers={"Authorization": f"Bearer {admin_tokens['access_token']}"})
    assert resp.status_code == 422


# ── Users: Update Role ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_user_role(client, admin_tokens):
    """admin 修改用户激活状态 → 修改生效；角色字段已被禁用。"""
    # 创建测试用户
    cresp = await client.post("/api/v1/users/batch", json={
        "usernames": ["role_test"],
    }, headers={"Authorization": f"Bearer {admin_tokens['access_token']}"})
    user = cresp.json()["data"][0]
    user_id = user["user_id"]

    # 修改激活状态
    resp = await client.patch(f"/api/v1/users/{user_id}", json={
        "is_active": False,
    }, headers={"Authorization": f"Bearer {admin_tokens['access_token']}"})
    assert resp.status_code == 200
    assert resp.json()["data"]["is_active"] is False

    # 恢复激活状态
    resp = await client.patch(f"/api/v1/users/{user_id}", json={
        "is_active": True,
    }, headers={"Authorization": f"Bearer {admin_tokens['access_token']}"})
    assert resp.status_code == 200
    assert resp.json()["data"]["is_active"] is True


# ── Users: Delete ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_user(client, admin_tokens):
    """admin 删除用户 → 被删用户的 refresh_token 失效。"""
    # 创建测试用户
    cresp = await client.post("/api/v1/users/batch", json={
        "usernames": ["to_delete"],
    }, headers={"Authorization": f"Bearer {admin_tokens['access_token']}"})
    user = cresp.json()["data"][0]
    user_id = user["user_id"]
    user_pw = user["password"]

    # 以该用户身份登录获取 refresh_token
    login_resp = await client.post("/api/v1/auth/login", json={
        "username": "to_delete", "password": user_pw,
    })
    user_refresh = login_resp.json()["data"]["refresh_token"]

    # admin 删除该用户
    resp = await client.delete(f"/api/v1/users/{user_id}", headers={
        "Authorization": f"Bearer {admin_tokens['access_token']}",
    })
    assert resp.status_code == 200

    # 被删除用户的 refresh_token 应失效
    refresh_resp = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": user_refresh,
    })
    assert refresh_resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_self_forbidden(client, admin_tokens):
    """admin 不能删除自己 → 400。"""
    resp = await client.delete(f"/api/v1/users/{admin_tokens['user_id']}", headers={
        "Authorization": f"Bearer {admin_tokens['access_token']}",
    })
    assert resp.status_code == 400


# ── Users: Reset Password ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reset_password(client, admin_tokens):
    """admin 重置密码 → 旧密码失效，新密码可登录，旧 refresh_token 失效。"""
    # 创建测试用户
    cresp = await client.post("/api/v1/users/batch", json={
        "usernames": ["reset_test"],
    }, headers={"Authorization": f"Bearer {admin_tokens['access_token']}"})
    user = cresp.json()["data"][0]
    user_id = user["user_id"]
    old_pw = user["password"]

    # 用户登录获取 refresh_token
    login_resp = await client.post("/api/v1/auth/login", json={
        "username": "reset_test", "password": old_pw,
    })
    old_refresh = login_resp.json()["data"]["refresh_token"]

    # admin 重置密码
    resp = await client.post(f"/api/v1/users/{user_id}/reset-password", headers={
        "Authorization": f"Bearer {admin_tokens['access_token']}",
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    new_pw = data["new_password"]
    assert new_pw != old_pw
    assert data["user_id"] == user_id
    assert data["username"] == "reset_test"
    assert isinstance(data["username"], str)

    # 旧密码登录失败
    old_login = await client.post("/api/v1/auth/login", json={
        "username": "reset_test", "password": old_pw,
    })
    assert old_login.status_code == 401

    # 旧 refresh_token 失效（token_version 已 bump）
    refresh_resp = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": old_refresh,
    })
    assert refresh_resp.status_code == 401

    # 新密码可登录
    new_login = await client.post("/api/v1/auth/login", json={
        "username": "reset_test", "password": new_pw,
    })
    assert new_login.status_code == 200


# ── Home directory ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_home_dir_created(client, admin_tokens):
    """创建用户时自动生成 home 目录。"""
    import os
    from app.config import settings

    # admin home 目录
    admin_home = os.path.join(settings.AGENTOS_HOME_BASE, "admin")
    assert os.path.isdir(admin_home)

    # 新用户 home 目录
    cresp = await client.post("/api/v1/users/batch", json={
        "usernames": ["home_test"],
    }, headers={"Authorization": f"Bearer {admin_tokens['access_token']}"})
    assert cresp.status_code == 200
    user_home = os.path.join(settings.AGENTOS_HOME_BASE, "home_test")
    assert os.path.isdir(user_home)


# ── Auth: No-auth endpoints ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unauthorized_access(client):
    """未认证访问受保护端点 → 401。"""
    resp = await client.get("/api/v1/auth/permissions")
    assert resp.status_code == 401
