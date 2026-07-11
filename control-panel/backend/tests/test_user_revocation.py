"""UserRevocation 模型测试。

验证 token 撤销表的结构定义正确。
"""
from app.models.user_revocation import UserRevocation


def test_user_revocation_model_exists():
    """UserRevocation 模型表名为 user_revocation。"""
    assert UserRevocation.__tablename__ == "user_revocation"


def test_user_revocation_has_required_columns():
    """UserRevocation 包含必需字段：user_id, revoked_after, updated_at。"""
    columns = {c.name for c in UserRevocation.__table__.columns}
    assert "user_id" in columns
    assert "revoked_after" in columns
    assert "updated_at" in columns
