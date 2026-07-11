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

from app.config import settings

# 临时 home 目录，避免污染真实路径
TEST_HOME = "/tmp/agentos_test_home"

# 测试数据文件路径
TEST_DATA_PATH = Path(__file__).parent / "test_data.json"


def load_test_data() -> dict:
    """从 test_data.json 加载测试数据。"""
    with open(TEST_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest_asyncio.fixture
async def backend():
    """提供一个已启动的 LocalUsersBackend，使用内存 SQLite，测试后自动清理。"""
    from app.services import get_user_backend, reset_user_backend

    data = load_test_data()

    # 覆盖配置：使用内存数据库 + 临时目录 + 测试管理员凭据
    settings.DATABASE_URL = "sqlite+aiosqlite://"
    settings.USER_SYSTEM_BACKEND = "local-users"
    settings.AGENTOS_HOME_BASE = TEST_HOME
    settings.AGENTOS_ADMIN_USERNAME = data["admin"]["username"]
    settings.AGENTOS_ADMIN_PASSWORD = data["admin"]["password"]

    # 重置单例缓存，确保每次测试使用新配置
    reset_user_backend()
    b = get_user_backend()
    await b.on_startup()
    await b.seed_initial_admin()

    yield b

    # 清理：关闭引擎、重置缓存、删除临时目录
    await b.on_shutdown()
    reset_user_backend()
    if os.path.isdir(TEST_HOME):
        shutil.rmtree(TEST_HOME, ignore_errors=True)


@pytest_asyncio.fixture
def test_data():
    """提供测试数据字典。"""
    return load_test_data()
