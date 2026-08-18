"""LocalUsersBackend 集成测试。

覆盖用户 CRUD、认证、密码管理、home 目录生命周期等核心功能。
使用 conftest.py 的 backend fixture（内存 SQLite，无需外部数据库）。
测试数据从 test_data.json 加载。
"""
import os
import shutil
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


@pytest.mark.asyncio
async def test_seed_initial_admin_recreates_missing_home(backend, test_data):
    """DB 中已存在 admin 但家目录整体缺失 → seed 重建 home 和 .jiuwenswarm。"""
    username = test_data["admin"]["username"]
    home = os.path.join(settings.AGENTOS_HOME_BASE, username)
    shutil.rmtree(home, ignore_errors=True)
    assert not os.path.isdir(home)

    await backend.seed_initial_admin()

    assert os.path.isdir(home)
    assert os.path.isdir(os.path.join(home, ".jiuwenswarm"))
    assert os.path.isfile(os.path.join(home, ".jiuwenswarm", "config", "config.yaml"))


@pytest.mark.asyncio
async def test_seed_initial_admin_home_exists_untouched(backend, test_data):
    """家目录已存在 → seed 不改动已有内容。"""
    username = test_data["admin"]["username"]
    home = os.path.join(settings.AGENTOS_HOME_BASE, username)
    os.makedirs(home, exist_ok=True)
    jwswarm = os.path.join(home, ".jiuwenswarm")
    os.makedirs(jwswarm, exist_ok=True)
    marker = os.path.join(jwswarm, "config", "user-extra.yaml")
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    Path(marker).write_text("user: data", encoding="utf-8")

    await backend.seed_initial_admin()

    assert Path(marker).read_text(encoding="utf-8") == "user: data"


@pytest.mark.asyncio
async def test_seed_initial_admin_litellm_409_already_exists(
    backend, test_data, monkeypatch
):
    """LiteLLM 对已存在用户返回 409 → seed 视为已存在跳过，仍继续重建家目录。

    回归：此前只认 400，409 会走进 else 提前 return，家目录/Key/config
    的自愈逻辑永远不执行（实测 LiteLLM 返回 409 "User with id xxx already exists"）。
    """
    from unittest.mock import AsyncMock

    from app.services.litellm_service import LitellmUpstreamError

    username = test_data["admin"]["username"]
    home = os.path.join(settings.AGENTOS_HOME_BASE, username)
    shutil.rmtree(home, ignore_errors=True)
    assert not os.path.isdir(home)

    mock_svc = AsyncMock()
    mock_svc.create_user = AsyncMock(
        side_effect=LitellmUpstreamError(409, "User with id xxx already exists")
    )

    import app.services as services_module

    monkeypatch.setattr(services_module, "get_litellm_svc", lambda: mock_svc)

    await backend.seed_initial_admin()

    assert os.path.isdir(home)
    assert os.path.isdir(os.path.join(home, ".jiuwenswarm"))
    assert os.path.isfile(os.path.join(home, ".jiuwenswarm", "config", "config.yaml"))


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


@pytest.mark.asyncio
async def test_delete_user_with_default_key_cleans_up_keys(backend, monkeypatch):
    """删除带默认 Key 标记的用户 → 成功，且 litellm_user_key / user_default_key 全部清理。

    复现生产 500 根因：delete_user 先删 litellm_user_key，会因 user_default_key 的
    外键引用（key_id → litellm_user_key.id）而失败（NO ACTION）。PostgreSQL 下该语句
    失败会把事务打入 aborted 状态，后续 commit 抛 InFailedSQLTransactionError。
    修复要求：先删子表 user_default_key，且 best-effort 清理不得污染主事务。
    """
    from sqlalchemy import func, select

    # 需在 backend fixture 初始化引擎之后导入（模块级导入会拿到 None）
    from app.database import async_session_maker
    from app.models.base import Base
    from app.models.litellm_user_key import LitellmUserKey
    from app.models.user_default_key import UserDefaultKey
    from app.services.local_users.models import User
    from app.services.local_users.password import hash_password

    engine = backend.get_engine()
    assert engine is not None

    # 启用外键约束，复现生产 PostgreSQL 的 FK 行为（内存 SQLite 默认不启用）
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON")

    # 确保 litellm_user_key / user_default_key 表已建
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 直接造数据：用户 + 一条 litellm_user_key + 指向它的默认 Key 标记
    async with async_session_maker() as s:
        user = User(
            username="fkdel_user", hashed_password=hash_password("TestPass123")
        )
        s.add(user)
        await s.flush()
        key = LitellmUserKey(
            uid=str(user.id),
            key_alias="default",
            key_name="default",
            key="encrypted-placeholder",
        )
        s.add(key)
        await s.flush()
        s.add(UserDefaultKey(uid=str(user.id), key_id=key.id))
        await s.commit()
        user_id = user.id
        uid = str(user_id)

    # 让 get_litellm_svc 返回只做本地 Key 清理的假服务（跳过真实 LiteLLM 上游）
    import app.services as svc_mod

    class _FakeLiteLLMSvc:
        async def delete_user(self, db, uid):
            await LitellmUserKey.delete_by_uid(db, uid)

    monkeypatch.setattr(svc_mod, "get_litellm_svc", lambda: _FakeLiteLLMSvc())

    # 执行删除
    await backend.delete_user(user_id)

    # 断言：用户、litellm_user_key、user_default_key 全部清理
    assert await backend.get_user_by_id(user_id) is None
    async with async_session_maker() as s:
        n_keys = (
            await s.execute(
                select(func.count())
                .select_from(LitellmUserKey)
                .where(LitellmUserKey.uid == uid)
            )
        ).scalar()
        n_marks = (
            await s.execute(
                select(func.count())
                .select_from(UserDefaultKey)
                .where(UserDefaultKey.uid == uid)
            )
        ).scalar()
    assert n_keys == 0
    assert n_marks == 0


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
async def test_delete_user_home_removal_failure_logs_warning(
    backend, monkeypatch, caplog
):
    """删除用户时 home 删除失败 → 记 warning，DB 用户仍被删除，家目录残留。"""
    import app.services.local_users.backend as backend_module

    username = "delwarn"
    record, _ = await backend.create_user(username)
    user_id = uuid.UUID(record.user_id)
    home = os.path.join(settings.AGENTOS_HOME_BASE, username)
    assert os.path.isdir(home)

    # 模拟 home 删除失败（不执行真实删除）
    monkeypatch.setattr(backend_module, "_remove_home", lambda username: None)

    with caplog.at_level("WARNING", logger="app.services.local_users.backend"):
        await backend.delete_user(user_id)

    # DB 用户已删除，家目录残留 + warning 日志
    assert await backend.get_user_by_id(user_id) is None
    assert os.path.isdir(home)
    assert any("家目录删除失败" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_jwswarm_config_copied_on_user_create(backend, test_data):
    """创建用户 → 自动复制 .jiuwenswarm 目录及内容。"""
    username = test_data["users"]["auto_password"][6]
    await backend.create_user(username)
    jwswarm_dir = os.path.join(settings.AGENTOS_HOME_BASE, username, ".jiuwenswarm")
    assert os.path.isdir(jwswarm_dir)
    config_file = os.path.join(jwswarm_dir, "config", "config.yaml")
    assert os.path.isfile(config_file)
    content = Path(config_file).read_text(encoding="utf-8")
    assert "models:" in content


@pytest.mark.asyncio
async def test_create_user_home_already_exists(backend, test_data, caplog):
    """家目录已存在（如删除用户时残留）→ 整目录删除后从模板全新重建，遗留文件被清掉并记 warning。"""
    username = test_data["users"]["auto_password"][7]
    home = os.path.join(settings.AGENTOS_HOME_BASE, username)
    os.makedirs(home, exist_ok=True)
    # 模拟残留旧 .jiuwenswarm
    old_jwswarm = os.path.join(home, ".jiuwenswarm")
    os.makedirs(os.path.join(old_jwswarm, "config"), exist_ok=True)
    Path(old_jwswarm, "config", "config.yaml").write_text("old: true", encoding="utf-8")
    # 模拟旧的非模板用户文件（整目录重建后应被清除）
    Path(old_jwswarm, "config", "user-extra.yaml").write_text("user: data", encoding="utf-8")

    with caplog.at_level("WARNING", logger="app.services.local_users.backend"):
        await backend.create_user(username)

    # 整目录已重建：config.yaml 为全新模板内容
    new_config = os.path.join(home, ".jiuwenswarm", "config", "config.yaml")
    assert os.path.isfile(new_config)
    new_content = Path(new_config).read_text(encoding="utf-8")
    assert "models:" in new_content
    assert "defaults" in new_content
    # 旧的非模板用户文件已被清除
    assert not os.path.exists(
        os.path.join(home, ".jiuwenswarm", "config", "user-extra.yaml")
    )
    # 删除前已记录 warning
    assert any("家目录已存在" in rec.message for rec in caplog.records)


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


class TestSyncAllUsersAgentos:
    """agentos 全量同步：单用户失败必须隔离，不影响其他用户。"""

    async def test_single_user_failure_does_not_block_others(self, backend, monkeypatch):
        """回归：一个用户重建失败（事务失效）不影响后续用户。

        此前所有用户共用一个 session，某用户重建异常后事务进入 abort 状态，
        后续用户的所有 SQL 都会抛 InFailedSQLTransactionError（PG）/
        PendingRollbackError（SQLAlchemy 通用），整个同步被单个用户拖垮。
        现在每个用户独立 session，失败只影响其自身事务。
        """
        import app.services.local_users.backend as backend_module
        from app.models.litellm_user_key import LitellmUserKey
        from app.services.local_users.backend import _sync_all_users_agentos
        from sqlalchemy import select

        await backend.create_user("syncuser1")
        await backend.create_user("syncuser2")

        processed = []
        first = True

        async def fake_rebuild(session, username, filtered_models):
            nonlocal first
            if first:
                # 第一个被处理的用户：在本 session 触发 flush 失败，
                # 事务失效（等效 PG 的 abort），后续同 session SQL 全部报错
                first = False
                session.add(LitellmUserKey(uid="x", key_alias="dup", key=None))
                await session.flush()
                return
            # 其余用户：必须能正常执行 SQL
            await session.execute(select(LitellmUserKey))
            processed.append(username)

        monkeypatch.setattr(backend_module, "_rebuild_user_agentos", fake_rebuild)

        await _sync_all_users_agentos()

        # 共 3 个用户（admin + 2 新建），首个失败，其余 2 个必须仍被处理
        assert len(processed) == 2

    async def test_rebuild_user_agentos_writes_default_key(self, backend):
        """重建 agentos：用默认 Key（litellm_user_key.id）写入 config.yaml。

        回归：此前先按 key_alias 查默认 Key（传入的是 int id），再按 id 兜底；
        现在直接按 id 查，避免类型不匹配。
        """
        from app.database import async_session_maker
        from app.services.local_users.backend import _rebuild_user_agentos

        await backend.create_user("rebuildkey")

        async with async_session_maker() as session:
            await _rebuild_user_agentos(session, "rebuildkey", [("test-model", 4096)])

        config_path = (
            Path(settings.AGENTOS_HOME_BASE)
            / "rebuildkey"
            / ".jiuwenswarm"
            / "config"
            / "config.yaml"
        )
        text = config_path.read_text(encoding="utf-8")
        assert "test-model" in text
        assert "sk-test" in text  # conftest 的 stub Key 前缀

    async def test_rebuild_creates_missing_default_key(self, backend, monkeypatch):
        """默认 Key 缺失时：经 LiteLLM 新建并设为默认，写入 config.yaml。"""
        from unittest.mock import AsyncMock

        import app.services as svc_mod
        from app.database import async_session_maker
        from app.models.litellm_user_key import LitellmUserKey
        from app.models.user_default_key import UserDefaultKey
        from app.services.local_users.backend import _rebuild_user_agentos
        from app.services.local_users.models import User
        from sqlalchemy import delete, select

        await backend.create_user("rebuildnokey")

        # 删掉 Key + 默认标记，模拟默认 Key 缺失
        async with async_session_maker() as s:
            user = (
                await s.execute(select(User).where(User.username == "rebuildnokey"))
            ).scalar_one()
            uid = str(user.id)
            await s.execute(delete(LitellmUserKey).where(LitellmUserKey.uid == uid))
            await s.execute(delete(UserDefaultKey).where(UserDefaultKey.uid == uid))
            await s.commit()

        # mock LiteLLM svc：apply_key 真正落一条 Key 记录，并返回新 Key
        async def fake_apply_key(db, uid, model=None, key_name=None):
            rec = LitellmUserKey(
                uid=uid, key_alias="default-key", key="sk-new-" + "n" * 40
            )
            db.add(rec)
            await db.flush()
            return {"key": "sk-new-" + "n" * 40, "key_id": rec.id}

        mock_svc = AsyncMock()
        mock_svc.apply_key = fake_apply_key
        monkeypatch.setattr(svc_mod, "get_litellm_svc", lambda: mock_svc)

        async with async_session_maker() as s:
            await _rebuild_user_agentos(s, "rebuildnokey", [("rebuild-model", 2048)])

        # 默认标记已重建，config.yaml 写入新 Key
        async with async_session_maker() as s:
            assert await UserDefaultKey.get_by_uid(s, uid) is not None
        config_path = (
            Path(settings.AGENTOS_HOME_BASE)
            / "rebuildnokey"
            / ".jiuwenswarm"
            / "config"
            / "config.yaml"
        )
        text = config_path.read_text(encoding="utf-8")
        assert "rebuild-model" in text
        assert "sk-new-" in text

    async def test_rebuild_missing_default_key_without_litellm_skips(
        self, backend, monkeypatch, caplog
    ):
        """默认 Key 缺失且 LiteLLM 不可用时：跳过、不新建、config 不变，且日志告警。"""
        import logging

        import app.services as svc_mod
        from app.database import async_session_maker
        from app.models.litellm_user_key import LitellmUserKey
        from app.models.user_default_key import UserDefaultKey
        from app.services.local_users.backend import _rebuild_user_agentos
        from app.services.local_users.models import User
        from sqlalchemy import delete, select

        await backend.create_user("rebuildskip")

        async with async_session_maker() as s:
            user = (
                await s.execute(select(User).where(User.username == "rebuildskip"))
            ).scalar_one()
            uid = str(user.id)
            await s.execute(delete(LitellmUserKey).where(LitellmUserKey.uid == uid))
            await s.execute(delete(UserDefaultKey).where(UserDefaultKey.uid == uid))
            await s.commit()

        monkeypatch.setattr(svc_mod, "get_litellm_svc", lambda: None)

        with caplog.at_level(logging.WARNING):
            async with async_session_maker() as s:
                await _rebuild_user_agentos(s, "rebuildskip", [("skip-model", 2048)])

        # 跳过必须留下告警，能定位到具体用户
        assert "rebuildskip" in caplog.text
        assert "重建跳过" in caplog.text

        async with async_session_maker() as s:
            assert await UserDefaultKey.get_by_uid(s, uid) is None
        config_path = (
            Path(settings.AGENTOS_HOME_BASE)
            / "rebuildskip"
            / ".jiuwenswarm"
            / "config"
            / "config.yaml"
        )
        text = config_path.read_text(encoding="utf-8")
        assert "skip-model" not in text
