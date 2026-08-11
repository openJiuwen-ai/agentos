"""LocalUsersBackend 集成测试。

覆盖用户 CRUD、认证、密码管理、home 目录生命周期等核心功能。
使用 conftest.py 的 backend fixture（内存 SQLite，无需外部数据库）。
测试数据从 test_data.json 加载。
"""
import os
import uuid
from pathlib import Path

import pytest

from app.config import settings
from app.schemas.user import ListUsersParams


# ── 管理员初始化 ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_seed_initial_admin(backend, test_data):
    """初始化管理员：创建 admin 用户 + home 目录。"""
    admin = test_data["admin"]
    user = await backend.get_user_by_username(admin["username"])
    assert user is not None
    assert user.role == "admin"
    assert user.is_active is True
    assert os.path.isdir(os.path.join(settings.AGENTOS_HOME_BASE, admin["username"]))


@pytest.mark.asyncio
async def test_seed_initial_admin_idempotent(backend):
    """重复初始化管理员不会报错，也不会产生重复用户。"""
    await backend.seed_initial_admin()
    result = await backend.list_users(
        ListUsersParams(page=1, page_size=100)
    )
    assert result.total == 1


# ── 认证 ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_authenticate_success(backend, test_data):
    """正确用户名+密码 → 返回 UserCredentials。"""
    admin = test_data["admin"]
    creds = await backend.authenticate(admin["username"], admin["password"])
    assert creds is not None
    assert creds.username == admin["username"]
    assert creds.role == "admin"
    assert creds.is_active is True


@pytest.mark.asyncio
async def test_authenticate_wrong_password(backend, test_data):
    """错误密码 → 返回 None。"""
    admin = test_data["admin"]
    creds = await backend.authenticate(admin["username"], test_data["passwords"]["wrong"])
    assert creds is None


@pytest.mark.asyncio
async def test_authenticate_nonexistent_user(backend):
    """不存在的用户 → 返回 None（不泄露用户是否存在）。"""
    creds = await backend.authenticate("nobody", "x")
    assert creds is None


# ── 创建用户 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_user(backend, test_data):
    """创建用户（不指定密码）→ 自动生成密码。"""
    username = test_data["users"]["auto_password"][0]
    record, generated_pw = await backend.create_user(username)
    assert record.username == username
    assert record.role == "user"
    assert generated_pw is not None
    assert len(generated_pw) >= 12


@pytest.mark.asyncio
async def test_create_user_with_password(backend, test_data):
    """创建用户（指定密码）→ generated 返回 None，可用该密码登录。"""
    pw_data = test_data["users"]["with_password"]
    username, password = "bob", pw_data["bob"]
    record, generated = await backend.create_user(username, password=password)
    assert record.username == username
    assert generated is None
    creds = await backend.authenticate(username, password)
    assert creds is not None


@pytest.mark.asyncio
async def test_create_user_duplicate(backend):
    """创建重复用户名 → 抛出 USERNAME_ALREADY_EXISTS。"""
    await backend.create_user("dave")
    with pytest.raises(ValueError, match="USERNAME_ALREADY_EXISTS"):
        await backend.create_user("dave")


@pytest.mark.asyncio
async def test_create_user_invalid_username(backend):
    """无效用户名（过短/含非法字符）→ 抛出 ValueError。"""
    with pytest.raises(ValueError):
        await backend.create_user("ab")      # 长度不足 3
    with pytest.raises(ValueError):
        await backend.create_user("A B!")    # 含空格和特殊字符


# ── 查询用户 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_user_by_id(backend, test_data):
    """按 UUID 查询 → 返回对应用户。"""
    username = test_data["users"]["auto_password"][1]
    record, _ = await backend.create_user(username)
    user_id = uuid.UUID(record.user_id)
    found = await backend.get_user_by_id(user_id)
    assert found is not None
    assert found.username == username


@pytest.mark.asyncio
async def test_get_user_by_id_not_found(backend):
    """查询不存在的 UUID → 返回 None。"""
    found = await backend.get_user_by_id(uuid.uuid4())
    assert found is None


@pytest.mark.asyncio
async def test_get_user_by_username(backend, test_data):
    """按用户名查询 → 返回对应用户。"""
    username = test_data["users"]["auto_password"][2]
    await backend.create_user(username)
    found = await backend.get_user_by_username(username)
    assert found is not None
    assert found.username == username


# ── 列表与分页 ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_users(backend, test_data):
    """列出用户 → 包含 admin + 新创建的用户。"""
    batch = test_data["users"]["batch"]
    for name in batch[:2]:
        await backend.create_user(name)
    result = await backend.list_users(ListUsersParams())
    assert result.total >= 3  # admin + batch[0] + batch[1]
    usernames = [u.username for u in result.items]
    assert test_data["admin"]["username"] in usernames
    assert batch[0] in usernames
    assert batch[1] in usernames


@pytest.mark.asyncio
async def test_list_users_pagination(backend, test_data):
    """分页参数生效 → 返回指定数量的记录。"""
    batch = test_data["users"]["batch"]
    for name in batch[2:4]:
        await backend.create_user(name)
    result = await backend.list_users(ListUsersParams(page=1, page_size=2))
    assert len(result.items) <= 2
    assert result.total >= 3


# ── 更新用户 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_user_role(backend, test_data):
    """更新用户角色 → 角色变更生效。"""
    username = test_data["users"]["auto_password"][3]
    record, _ = await backend.create_user(username)
    user_id = uuid.UUID(record.user_id)
    updated = await backend.update_user(user_id, {"role": "admin"})
    assert updated.role == "admin"


@pytest.mark.asyncio
async def test_update_user_not_found(backend):
    """更新不存在的用户 → 抛出 ValueError。"""
    with pytest.raises(ValueError):
        await backend.update_user(uuid.uuid4(), {"role": "admin"})


# ── 删除用户 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_user(backend, test_data):
    """删除用户 → 查询返回 None。"""
    pw_data = test_data["users"]["with_password"]
    username, password = "to_delete", pw_data["to_delete"]
    record, _ = await backend.create_user(username, password=password)
    user_id = uuid.UUID(record.user_id)
    await backend.delete_user(user_id)
    found = await backend.get_user_by_id(user_id)
    assert found is None


@pytest.mark.asyncio
async def test_delete_user_not_found(backend):
    """删除不存在的用户 → 抛出 ValueError。"""
    with pytest.raises(ValueError):
        await backend.delete_user(uuid.uuid4())


# ── 密码管理 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_change_password(backend, test_data):
    """修改密码 → 旧密码失效，新密码生效。"""
    pw_data = test_data["users"]["with_password"]
    passwords = test_data["passwords"]
    record, _ = await backend.create_user("chpwd", password=pw_data["chpwd"])
    user_id = uuid.UUID(record.user_id)
    await backend.change_password(user_id, pw_data["chpwd"], passwords["new"])

    # 旧密码登录失败
    creds = await backend.authenticate("chpwd", pw_data["chpwd"])
    assert creds is None

    # 新密码登录成功
    creds = await backend.authenticate("chpwd", passwords["new"])
    assert creds is not None


@pytest.mark.asyncio
async def test_change_password_wrong_old(backend, test_data):
    """旧密码错误 → 抛出 ValueError（原密码错误）。"""
    pw_data = test_data["users"]["with_password"]
    passwords = test_data["passwords"]
    record, _ = await backend.create_user("chpwd2", password=pw_data["chpwd2"])
    user_id = uuid.UUID(record.user_id)
    with pytest.raises(ValueError, match="原密码错误"):
        await backend.change_password(user_id, passwords["wrong_old"], passwords["new"])


@pytest.mark.asyncio
async def test_change_password_too_short(backend, test_data):
    """新密码不足 8 位 → 抛出 ValueError。"""
    pw_data = test_data["users"]["with_password"]
    passwords = test_data["passwords"]
    record, _ = await backend.create_user("chpwd3", password=pw_data["chpwd3"])
    user_id = uuid.UUID(record.user_id)
    with pytest.raises(ValueError, match="密码长度需为 8-64 位"):
        await backend.change_password(user_id, pw_data["chpwd3"], passwords["too_short"])


@pytest.mark.asyncio
async def test_reset_password(backend, test_data):
    """管理员重置密码 → 返回新密码，旧密码失效。"""
    pw_data = test_data["users"]["with_password"]
    record, _ = await backend.create_user("resetpw", password=pw_data["resetpw"])
    user_id = uuid.UUID(record.user_id)

    new_pw = await backend.reset_password(user_id)
    assert new_pw != pw_data["resetpw"]
    assert len(new_pw) >= 12

    # 旧密码登录失败
    creds = await backend.authenticate("resetpw", pw_data["resetpw"])
    assert creds is None

    # 新密码登录成功
    creds = await backend.authenticate("resetpw", new_pw)
    assert creds is not None


# ── Home 目录 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_home_directory_created_on_user_create(backend, test_data):
    """创建用户 → 自动生成 home 目录。"""
    username = test_data["users"]["auto_password"][4]
    await backend.create_user(username)
    home = os.path.join(settings.AGENTOS_HOME_BASE, username)
    assert os.path.isdir(home)


@pytest.mark.asyncio
async def test_home_directory_removed_on_user_delete(backend, test_data):
    """删除用户 → home 目录被清理。"""
    username = test_data["users"]["auto_password"][5]
    record, _ = await backend.create_user(username)
    home = os.path.join(settings.AGENTOS_HOME_BASE, username)
    assert os.path.isdir(home)
    await backend.delete_user(uuid.UUID(record.user_id))
    assert not os.path.isdir(home)


@pytest.mark.asyncio
async def test_jwswarm_config_copied_on_user_create(backend, test_data):
    """创建用户 → 自动复制 .jiuwenswarm 目录及内容。"""
    username = test_data["users"]["auto_password"][6]
    await backend.create_user(username)
    jwswarm_dir = os.path.join(settings.AGENTOS_HOME_BASE, username, ".jiuwenswarm")
    assert os.path.isdir(jwswarm_dir)
    assert os.path.isfile(os.path.join(jwswarm_dir, "config", "config.yaml"))


@pytest.mark.asyncio
async def test_create_user_home_already_exists(backend, test_data):
    """家目录已存在（如重装后重建同名用户）→ 仍然成功，.jiuwenswarm 被覆盖写入。"""
    username = test_data["users"]["auto_password"][7]
    home = os.path.join(settings.AGENTOS_HOME_BASE, username)
    os.makedirs(home, exist_ok=True)
    # 模拟已有 .jiuwenswarm
    old_jwswarm = os.path.join(home, ".jiuwenswarm")
    os.makedirs(os.path.join(old_jwswarm, "config"), exist_ok=True)
    Path(old_jwswarm, "config", "config.yaml").write_text("old: true", encoding="utf-8")

    await backend.create_user(username)

    # .jiuwenswarm 应该已更新为模板内容
    new_content = Path(old_jwswarm, "config", "config.yaml").read_text(encoding="utf-8")
    assert "models:" in new_content
    assert "defaults" in new_content


@pytest.mark.asyncio
async def test_create_user_without_swarm_template(backend, test_data, tmp_path):
    """swarm 模板目录不存在 → 跳过复制，用户创建仍然成功。"""
    import app.database as _db
    settings.AGENTOS_SWARM_TEMPLATE_DIR = str(tmp_path / "nonexistent")
    username = test_data["users"]["auto_password"][8]
    record, _ = await backend.create_user(username)
    assert record is not None
    home = os.path.join(settings.AGENTOS_HOME_BASE, username)
    assert os.path.isdir(home)
    # .jiuwenswarm 不应该存在
    assert not os.path.isdir(os.path.join(home, ".jiuwenswarm"))


# ── 引擎访问 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_engine(backend):
    """get_engine() 返回已初始化的异步引擎实例。"""
    engine = backend.get_engine()
    assert engine is not None


class TestChangePasswordStrength:
    """Integration tests for password strength enforcement in change_password."""

    async def test_rejects_too_short(self, backend):
        """change_password rejects passwords < 8 chars."""
        user, old_pwd = await backend.create_user("strengthtest1")
        with pytest.raises(ValueError) as exc:
            await backend.change_password(
                uuid.UUID(user.user_id), old_pwd, "Ab1"
            )
        assert "8-64" in str(exc.value)

    async def test_rejects_same_as_current(self, backend):
        """change_password rejects new password equal to current."""
        from app.services.local_users.password import hash_password
        old_pwd = "ValidPwd1"
        user, _ = await backend.create_user("strengthtest2", old_pwd)
        with pytest.raises(ValueError) as exc:
            await backend.change_password(
                uuid.UUID(user.user_id), old_pwd, old_pwd
            )
        assert "相同" in str(exc.value)

    async def test_accepts_strong_password(self, backend):
        """change_password succeeds with a strong new password."""
        user, _ = await backend.create_user("strengthtest3", "OldValid1")
        # First change the password to something so we know the old one
        await backend.change_password(
            uuid.UUID(user.user_id), "OldValid1", "NewValid2"
        )
        # If we get here, it succeeded — verify by authenticating
        creds = await backend.authenticate("strengthtest3", "NewValid2")
        assert creds is not None


class TestListUsersRoleFilter:
    """Integration tests for role filtering in list_users."""

    async def test_filter_admin_only(self, backend):
        """list_users(role='admin') returns only admins."""
        await backend.seed_initial_admin()
        await backend.create_user("filteruser1")
        result = await backend.list_users(ListUsersParams(role="admin"))
        assert all(u.role == "admin" for u in result.items)
        assert result.total >= 1

    async def test_filter_user_only(self, backend):
        """list_users(role='user') returns only non-admins."""
        await backend.seed_initial_admin()
        await backend.create_user("filteruser2")
        result = await backend.list_users(ListUsersParams(role="user"))
        assert all(u.role == "user" for u in result.items)

    async def test_filter_all(self, backend):
        """list_users without role returns all users."""
        await backend.seed_initial_admin()
        await backend.create_user("filteruser3")
        all_result = await backend.list_users(ListUsersParams())
        admin_result = await backend.list_users(ListUsersParams(role="admin"))
        user_result = await backend.list_users(ListUsersParams(role="user"))
        assert all_result.total == admin_result.total + user_result.total
