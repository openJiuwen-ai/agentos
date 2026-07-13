"""Test IAM layer adaptation — importability and interface contracts."""

import inspect


def test_tokens_module_importable():
    """TokenService 可导入，refresh_tokens 方法存在。"""
    from app.iam.tokens import TokenService
    assert hasattr(TokenService, "refresh_tokens")


def test_deps_has_get_db_session():
    """get_db_session 可调用（官方通过 app.iam.deps 暴露）。"""
    from app.iam.deps import get_db_session
    assert callable(get_db_session)


def test_refresh_tokens_accepts_optional_db():
    """refresh_tokens 的 db 参数接受 None（HTTP backend 场景不传 DB session）。"""
    from app.iam.tokens import TokenService
    sig = inspect.signature(TokenService.refresh_tokens)
    db_param = sig.parameters["db"]
    assert db_param.default is None or "None" in str(db_param.annotation), (
        "refresh_tokens should accept db: AsyncSession | None"
    )
