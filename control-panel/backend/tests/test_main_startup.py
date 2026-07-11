"""应用启动集成测试。"""


def test_main_app_importable():
    """验证 FastAPI app 可导入且标题正确。"""
    from app.main import app
    assert app.title == "AgentOS Panel — Backend API"
