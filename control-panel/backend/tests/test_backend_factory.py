"""测试注册表式后端工厂（app.services）。

工厂负责根据 settings.USER_SYSTEM_BACKEND 选择并缓存后端单例。
"""

from unittest.mock import patch

import pytest

from app.services import get_user_backend, register_backend, reset_user_backend, _BACKEND_REGISTRY


class DummyBackend:
    """用于测试的空后端桩类。"""
    pass


@pytest.fixture(autouse=True)
def _reset_backend():
    """每个测试前后重置后端单例缓存。"""
    reset_user_backend()
    yield
    reset_user_backend()


def test_get_user_backend_returns_singleton():
    """验证 get_user_backend() 返回同一实例（单例模式）。"""
    with patch("app.services._BACKEND_REGISTRY", {"test": "tests.test_backend_factory.DummyBackend"}):
        with patch("app.config.settings") as mock_settings:
            mock_settings.USER_SYSTEM_BACKEND = "test"
            b1 = get_user_backend()
            b2 = get_user_backend()
            assert b1 is b2


def test_register_backend_extends_registry():
    """验证 register_backend() 能动态注册新后端类型。"""
    register_backend("custom", "some.module.CustomBackend")
    assert "custom" in _BACKEND_REGISTRY
    # 清理：移除测试注册的后端
    del _BACKEND_REGISTRY["custom"]


def test_unknown_backend_raises():
    """验证配置了不存在的后端名称时抛出 ValueError。"""
    with patch("app.services._BACKEND_REGISTRY", {}):
        with patch("app.config.settings") as mock_settings:
            mock_settings.USER_SYSTEM_BACKEND = "nonexistent"
            try:
                get_user_backend()
                assert False, "Should raise ValueError"
            except ValueError as e:
                assert "Unknown backend" in str(e) or "Unknown USER_SYSTEM_BACKEND" in str(e)
