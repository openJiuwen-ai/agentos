"""测试 LitellmService 使用统计方法 — 直连 PG/SQLite 查询 LiteLLM_SpendLogs 表

每个用例的注释格式：
  [场景] 描述了什么样的输入条件和操作上下文
  [预期] 期望的输出结果或系统行为
"""

from unittest.mock import patch

import pytest

from sqlalchemy import text

from app.services.litellm_service import LitellmService


class TestLitellmServiceUsage:
    """使用统计 — 直连查询 LiteLLM_SpendLogs 表"""

    @pytest.fixture
    def svc(self):
        return LitellmService()

    # ── 辅助：建表 + 插数据 ──────────────────────────────────────────────

    async def _setup_table(self, db_session, rows: list[tuple]):
        """创建 LiteLLM_SpendLogs 表并插入测试数据。

        使用适配 SQLite / PostgreSQL 的通用写法。
        """
        await db_session.execute(text("DROP TABLE IF EXISTS \"LiteLLM_SpendLogs\""))
        await db_session.execute(text("""
            CREATE TABLE IF NOT EXISTS "LiteLLM_SpendLogs" (
                id TEXT PRIMARY KEY,
                "user" TEXT,
                model TEXT,
                "total_tokens" INTEGER DEFAULT 0,
                spend REAL DEFAULT 0,
                "startTime" TEXT
            )
        """))
        for r in rows:
            await db_session.execute(text("""
                INSERT INTO "LiteLLM_SpendLogs" (id, "user", model, "total_tokens", spend, "startTime")
                VALUES (:id, :user, :model, :tokens, :spend, :ts)
            """), {"id": r[0], "user": r[1], "model": r[2], "tokens": r[3], "spend": r[4], "ts": r[5]})
        await db_session.commit()

    # ── 测试用例 ──────────────────────────────────────────────────────────

    # [场景] 创建临时 spend 表，插入 3 条数据（2 天），按天聚合查询
    # [预期] 返回 items >= 1，granularity == "day"
    async def test_get_usage_trend(self, svc, db_session):
        await self._setup_table(db_session, [
            ("t1", "alice", "gpt-4", 150, 0.01, "2026-07-01 10:00:00"),
            ("t2", "alice", "gpt-4", 300, 0.02, "2026-07-01 14:00:00"),
            ("t3", "bob", "deepseek", 450, 0.03, "2026-07-02 09:00:00"),
        ])

        result = await svc.get_usage_trend(
            db_session, start_date="2026-07-01", end_date="2026-07-02",
        )
        assert len(result["items"]) >= 1
        assert result["granularity"] == "day"

    # [场景] 两部模型各 0.05 消费，按模型聚合
    # [预期] items 长度 2，每项 pct == 50.0
    async def test_get_usage_by_model(self, svc, db_session):
        await self._setup_table(db_session, [
            ("m1", "alice", "gpt-4", 500, 0.05, "2026-07-01 10:00:00"),
            ("m2", "bob", "deepseek", 500, 0.05, "2026-07-01 14:00:00"),
        ])

        result = await svc.get_usage_by_model(db_session, start_date="2026-07-01", end_date="2026-07-02")
        assert len(result["items"]) == 2
        for item in result["items"]:
            assert item["pct"] == 50.0

    # [场景] 3 个用户不同消费（bob 最高），取 Top 2
    # [预期] items 长度 2，bob 排第一
    async def test_get_usage_by_user(self, svc, db_session):
        await self._setup_table(db_session, [
            ("u1", "alice", "gpt-4", 100, 0.01, "2026-07-01 10:00:00"),
            ("u2", "bob", "deepseek", 500, 0.05, "2026-07-01 11:00:00"),
            ("u3", "charlie", "qwen", 200, 0.02, "2026-07-01 12:00:00"),
        ])

        result = await svc.get_usage_by_user(
            db_session, start_date="2026-07-01", end_date="2026-07-02", top=2,
        )
        assert len(result["items"]) == 2
        assert result["items"][0]["user_id"] == "bob"

    # [场景] 查询 alice 的每日用量（2 天数据 + bob 干扰数据）
    # [预期] daily_activity 长度 2，user_id == "alice"
    async def test_get_user_usage(self, svc, db_session):
        await self._setup_table(db_session, [
            ("d1", "alice", "gpt-4", 150, 0.03, "2026-07-01 08:00:00"),
            ("d2", "alice", "deepseek", 200, 0.02, "2026-07-01 16:00:00"),
            ("d3", "alice", "qwen", 300, 0.03, "2026-07-02 10:00:00"),
            ("d4", "bob", "gpt-4", 999, 9.99, "2026-07-01 12:00:00"),
        ])

        result = await svc.get_user_usage(
            db_session, user_id="alice", start_date="2026-07-01", end_date="2026-07-02",
        )
        assert result["user_id"] == "alice"
        assert len(result["daily_activity"]) == 2

    # [场景] 查询 2 天跨度的全部用户总览（3 条数据覆盖 alice + bob）
    # [预期] users 长度 2，daily 长度 2
    async def test_get_usage_overview(self, svc, db_session):
        await self._setup_table(db_session, [
            ("o1", "alice", "gpt-4", 100, 0.01, "2026-07-01 10:00:00"),
            ("o2", "bob", "deepseek", 200, 0.02, "2026-07-01 14:00:00"),
            ("o3", "alice", "qwen", 300, 0.03, "2026-07-02 09:00:00"),
        ])

        result = await svc.get_usage_overview(db_session, start_date="2026-07-01", end_date="2026-07-02")
        assert len(result["users"]) == 2
        assert len(result["daily"]) == 2
        assert result["daily"][0]["active_users"] == 2
        assert result["daily"][1]["active_users"] == 1

    # [场景] spend 表不存在时调用 get_usage_trend（触发表不存在的 ProgrammingError）
    # [预期] 返回空 items，不抛异常（优雅降级）
    async def test_spend_table_not_exists_graceful(self, svc, db_session):
        await db_session.execute(text("DROP TABLE IF EXISTS \"LiteLLM_SpendLogs\""))
        await db_session.commit()

        result = await svc.get_usage_trend(
            db_session, start_date="2026-07-01", end_date="2026-07-02",
        )
        assert result["items"] == []

    # [场景] DB 连接异常（非 ProgrammingError）时调用 _query_spend
    # [预期] 异常向上传播，不被吞掉
    async def test_spend_query_connection_error_propagates(self, svc, db_session):
        with patch.object(
            db_session, "execute",
            side_effect=OSError("Connection refused"),
        ):
            with pytest.raises(OSError, match="Connection refused"):
                await svc.get_usage_trend(
                    db_session, start_date="2026-07-01", end_date="2026-07-02",
                )
