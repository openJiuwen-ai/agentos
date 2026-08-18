"""测试公共 fixtures —— 提供内存数据库 + 临时 home 目录的 LocalUsersBackend 实例。

所有集成测试通过 backend fixture 获取一个已启动的后端：
- 使用 sqlite+aiosqlite://（内存数据库，无需外部服务）
- 自动创建 admin 用户
- 测试结束后清理临时目录并关闭引擎
"""

import json
import os
import shutil
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import settings

# 临时 home 目录，避免污染真实路径
TEST_HOME = "/tmp/agentos_test_home"
# 临时 swarm 模板目录
TEST_SWARM_TEMPLATE = "/tmp/agentos_test_swarm_template"

# 测试数据文件路径
TEST_DATA_PATH = Path(__file__).parent / "test_data.json"


def load_test_data() -> dict:
    """从 test_data.json 加载测试数据。"""
    with open(TEST_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _configure_for_test(data: dict) -> None:
    """覆盖配置为测试环境（内存 SQLite + 临时目录 + 测试管理员）。"""
    settings.AGENTOS_DATABASE_URL = "sqlite+aiosqlite://"
    settings.USER_SYSTEM_BACKEND = "local-users"
    settings.AGENTOS_HOME_BASE = TEST_HOME
    settings.AGENTOS_SWARM_TEMPLATE_DIR = TEST_SWARM_TEMPLATE
    settings.AGENTOS_SYS_UID = 1000
    settings.AGENTOS_SYS_GID = 1000
    settings.AGENTOS_ADMIN_USERNAME = data["admin"]["username"]
    settings.AGENTOS_ADMIN_PASSWORD = data["admin"]["password"]
    settings.AGENTOS_JWT_SECRET_KEY = "test-secret-key"
    settings.LITELLM_ADMIN_URL = "http://localhost:4000"
    settings.LITELLM_MASTER_KEY = "test-master-key"
    settings.LITELLM_KEY_ENCRYPTION_KEY = "0" * 64
    settings.LITELLM_DATABASE_URL = "sqlite+aiosqlite://"


def _cleanup_test_home() -> None:
    """清理测试 home 目录和模板目录。"""
    if os.path.isdir(TEST_HOME):
        shutil.rmtree(TEST_HOME, ignore_errors=True)
    if os.path.isdir(TEST_SWARM_TEMPLATE):
        shutil.rmtree(TEST_SWARM_TEMPLATE, ignore_errors=True)


def _register_litellm_svc_stub() -> None:
    """注册 LitellmService stub：mock 掉上游 HTTP，让 Key 申请写入本地内存库。

    生产环境由 main.py lifespan 调用 register_litellm_svc；测试 fixture 不触发
    lifespan，需手动注册，否则 LocalUsersBackend.create_user 因 svc=None 失败。
    """
    from unittest.mock import AsyncMock

    from app.services import register_litellm_svc
    from app.services.litellm_service import LitellmService

    svc = LitellmService()
    svc.request = AsyncMock(return_value={
        "key": "sk-test-" + "k" * 44,
        "key_name": "default-key",
    })
    register_litellm_svc(svc)


# ── 后端 fixture（直接测试 backend 接口） ─────────────────────────────


@pytest_asyncio.fixture
async def backend():
    """提供一个已启动的 LocalUsersBackend，使用内存 SQLite，测试后自动清理。"""
    from app.database import init_engine
    from app.services import get_user_backend, reset_user_backend

    data = load_test_data()
    _configure_for_test(data)
    _cleanup_test_home()
    _register_litellm_svc_stub()

    # 预导入所有 ORM 模型，确保 on_startup 的 create_all 覆盖全部表（首次 fixture 不遗漏）
    import app.models.litellm_model_params  # noqa: F401
    import app.models.litellm_user_key      # noqa: F401
    import app.models.user_default_key      # noqa: F401

    # 创建 swarm 模板目录及示例文件
    os.makedirs(os.path.join(TEST_SWARM_TEMPLATE, "config"), exist_ok=True)
    Path(TEST_SWARM_TEMPLATE, "config", "config.yaml").write_text("models:\n  defaults: []\n", encoding="utf-8")

    # 初始化共享数据库引擎
    init_engine()

    # 重置单例缓存，确保每次测试使用新配置
    reset_user_backend()
    b = get_user_backend()
    await b.on_startup()
    await b.seed_initial_admin()

    yield b

    # 清理：关闭引擎、重置缓存、删除临时目录
    await b.on_shutdown()
    reset_user_backend()
    _cleanup_test_home()

    import app.database as _db
    if _db.engine is not None:
        await _db.engine.dispose()
        _db.engine = None
        _db.async_session_maker = None


@pytest_asyncio.fixture
def test_data():
    """提供测试数据字典。"""
    return load_test_data()


# ── HTTP client fixtures（API 集成测试） ──────────────────────────────


@pytest_asyncio.fixture
async def client():
    """HTTP 测试客户端，连线到完整的 FastAPI 应用（local_users backend + IAM）。

    使用内存 SQLite，自动初始化数据库引擎、后端和 IAM 表。
    测试结束后清理临时目录并重置所有单例状态。
    """
    from app.database import init_engine
    from app.services import get_user_backend, reset_user_backend

    data = load_test_data()
    _configure_for_test(data)
    _cleanup_test_home()
    _register_litellm_svc_stub()

    # 预导入所有 ORM 模型，确保 on_startup 的 create_all 覆盖全部表
    import app.models.litellm_model_params  # noqa: F401
    import app.models.litellm_user_key      # noqa: F401
    import app.models.user_default_key      # noqa: F401

    # 创建 swarm 模板目录及示例文件
    os.makedirs(os.path.join(TEST_SWARM_TEMPLATE, "config"), exist_ok=True)
    Path(TEST_SWARM_TEMPLATE, "config", "config.yaml").write_text("models:\n  defaults: []\n", encoding="utf-8")

    # 清理上一个测试可能残留的引擎
    import app.database as _db
    if _db.engine is not None:
        await _db.engine.dispose()
        _db.engine = None
        _db.async_session_maker = None

    # 1. 初始化共享数据库引擎
    init_engine()

    # 2. 启动后端（建表 + 种子管理员）
    reset_user_backend()
    backend_obj = get_user_backend()
    await backend_obj.on_startup()
    await backend_obj.seed_initial_admin()

    # 3. 创建 IAM 表
    from app.iam.engine import ensure_iam_tables
    engine = backend_obj.get_engine()
    if engine is not None:
        await ensure_iam_tables(engine)

    # 4. 构建 HTTP 客户端（ASGITransport, 进程内通信）
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac

    # 5. 清理
    await backend_obj.on_shutdown()
    reset_user_backend()
    if _db.engine is not None:
        await _db.engine.dispose()
        _db.engine = None
        _db.async_session_maker = None
    _cleanup_test_home()


@pytest_asyncio.fixture
async def admin_tokens(request):
    """以 admin 身份登录，返回 token 数据（access_token, refresh_token, user_id 等）。"""
    data = load_test_data()
    test_client = request.getfixturevalue("client")
    resp = await test_client.post("/api/v1/auth/login", json={
        "username": data["admin"]["username"],
        "password": data["admin"]["password"],
    })
    if resp.status_code != 200:
        raise RuntimeError(
            f"admin_tokens fixture failed: expected 200, got {resp.status_code}"
        )
    return resp.json()["data"]
