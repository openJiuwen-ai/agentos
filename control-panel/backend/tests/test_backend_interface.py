"""测试 AbstractUserBackend 抽象接口。

确保所有后端必须实现的方法列表与基类定义一致。
"""
from abc import ABC

from app.services.base import AbstractUserBackend


def test_is_abstract_class():
    """验证 AbstractUserBackend 是抽象基类（不能直接实例化）。"""
    assert issubclass(AbstractUserBackend, ABC)


def test_has_required_methods():
    """验证抽象接口定义了所有必需方法（防止实现遗漏）。"""
    required = [
        "authenticate",         # 认证
        "get_user_by_id",       # 按 ID 查询用户
        "get_user_by_username", # 按用户名查询用户
        "list_users",           # 分页列出用户
        "create_user",          # 创建用户
        "update_user",          # 更新用户
        "delete_user",          # 删除用户
        "change_password",      # 修改密码
        "reset_password",       # 重置密码（管理员操作）
        "seed_initial_admin",   # 初始化管理员
        "on_startup",           # 启动生命周期
        "on_shutdown",          # 关闭生命周期
        "get_engine",           # 获取数据库引擎
    ]
    for method in required:
        assert hasattr(AbstractUserBackend, method), f"Missing method: {method}"


def test_cannot_instantiate_directly():
    """验证直接实例化抽象类会抛出 TypeError。"""
    try:
        AbstractUserBackend()
        assert False, "Should raise TypeError"
    except TypeError:
        pass
