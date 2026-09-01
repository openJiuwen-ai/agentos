"""测试 LitellmService 使用统计方法 — 直连 PG/SQLite 查询 LiteLLM_SpendLogs 表

每个用例的注释格式：
  [场景] 描述了什么样的输入条件和操作上下文
  [预期] 期望的输出结果或系统行为
"""

from unittest.mock import patch
from datetime import date

import pytest

from sqlalchemy import text

from app.services.litellm_service import LitellmService

# 复用 conftest 的测试引擎（StaticPool，共享连接），让 _query_spend(None, ...) 也能看到测试数据
from .conftest import _engine, _session_maker


class TestLitellmServiceUsage:
    """使用统计 — 直连查询 LiteLLM_SpendLogs 表"""

    @pytest.fixture
    def svc(self):
        s = LitellmService()
        # 让 _get_spend_session() 返回测试引擎的 session（StaticPool 共享连接）
        setattr(s, '_litellm_engine', _engine)
        setattr(s, '_litellm_sessionmaker', _session_maker)
        return s

    # ── 辅助：建表 + 插数据 ──────────────────────────────────────────────

    async def _setup_table(self, db_session, rows: list[dict]):
        """创建 LiteLLM_SpendLogs 表并插入测试数据。"""
        await db_session.execute(text('DROP TABLE IF EXISTS "LiteLLM_SpendLogs"'))
        await db_session.execute(text("""
            CREATE TABLE IF NOT EXISTS "LiteLLM_SpendLogs" (
                id TEXT PRIMARY KEY,
                "user" TEXT,
                model TEXT,
                model_id TEXT,
                model_group TEXT,
                "total_tokens" INTEGER DEFAULT 0,
                spend REAL DEFAULT 0,
                "startTime" TEXT,
                status TEXT,
                api_key TEXT
            )
        """))
        for r in rows:
            await db_session.execute(text("""
                INSERT INTO "LiteLLM_SpendLogs"
                    (id, "user", model, model_id, model_group, "total_tokens", spend, "startTime", status, api_key)
                VALUES
                    (:id, :user, :model, :model_id, :model_group, :tokens, :spend, :ts, :status, :api_key)
            """), r)
        await db_session.commit()

    async def _setup_tokens(self, db_session, tokens: list[str]):
        """创建 token 表（活跃 + 已删除）。"""
        for table in ('"LiteLLM_VerificationToken"',
                      '"LiteLLM_DeletedVerificationToken"'):
            await db_session.execute(text(f"DROP TABLE IF EXISTS {table}"))
            await db_session.execute(
                text(f"CREATE TABLE {table} (token TEXT PRIMARY KEY)"))
            for t in tokens:
                await db_session.execute(
                    text(f"INSERT INTO {table} (token) VALUES (:t)"),
                    {"t": t})
        await db_session.commit()

    async def _setup_proxy_models(self, db_session, models: dict[str, str]):
        """创建 LiteLLM_ProxyModelTable 并插入 model_id -> model_name 映射。"""
        await db_session.execute(
            text('DROP TABLE IF EXISTS "LiteLLM_ProxyModelTable"'))
        await db_session.execute(text("""
            CREATE TABLE IF NOT EXISTS "LiteLLM_ProxyModelTable" (
                model_id TEXT PRIMARY KEY,
                model_name TEXT
            )
        """))
        for mid, name in models.items():
            await db_session.execute(text("""
                INSERT INTO "LiteLLM_ProxyModelTable"
                    (model_id, model_name) VALUES (:mid, :name)
            """), {"mid": mid, "name": name})
        await db_session.commit()

    @staticmethod
    def _row(row_id: str, user: str, model: str, **kwargs) -> dict:
        """快捷构造一条 spend 记录，其余字段通过 kwargs 传入。"""
        base = {
            "id": row_id, "user": user, "model": model,
            "tokens": 0, "spend": 0.0,
            "ts": "2026-07-01 10:00:00",
            "model_id": "mid-default", "model_group": "",
            "status": "success", "api_key": "user-key-1",
        }
        base.update(kwargs)
        return base

    # ── 测试用例 ──────────────────────────────────────────────────────────

    # [场景] 创建临时 spend 表，插入 3 条数据（2 天），按天聚合查询
    # [预期] 返回 items >= 1，granularity == "day"
    async def test_get_usage_trend(self, svc, db_session):
        await self._setup_tokens(db_session, ["user-key-1"])
        await self._setup_table(db_session, [
            self._row("t1", "alice", "gpt-4",
                      tokens=150, spend=0.01, ts="2026-07-01 10:00:00"),
            self._row("t2", "alice", "gpt-4",
                      tokens=300, spend=0.02, ts="2026-07-01 14:00:00"),
            self._row("t3", "bob", "deepseek",
                      tokens=450, spend=0.03,
                      ts="2026-07-02 09:00:00", api_key="user-key-2"),
        ])

        result = await svc.get_usage_trend(
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 2),
        )
        assert len(result["items"]) >= 1
        assert result["granularity"] == "day"

    # [场景] 两个模型各有 0.05 消费，按模型聚合
    # [预期] items 长度 2，每项 pct == 50.0，模型名从 ProxyModelTable 映射
    async def test_get_usage_by_model(self, svc, db_session):
        await self._setup_tokens(db_session, ["user-key-1", "user-key-2"])
        await self._setup_proxy_models(
            db_session, {"mid-gpt4": "gpt-4", "mid-ds": "deepseek"})
        r1 = self._row("m1", "alice", "gpt-4", tokens=500, spend=0.05,
                        model_id="mid-gpt4", model_group="gpt-4",
                        api_key="user-key-1")
        r2 = self._row("m2", "bob", "deepseek", tokens=500, spend=0.05,
                        model_id="mid-ds", model_group="deepseek",
                        api_key="user-key-2")
        await self._setup_table(db_session, [r1, r2])

        result = await svc.get_usage_by_model(
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 2))
        assert len(result["items"]) == 2
        for item in result["items"]:
            assert item["pct"] == 50.0

    # [场景] 模型已删除（model_id 不在 ProxyModelTable 中）
    # [预期] 该模型归类为"已删除模型"
    async def test_get_usage_by_model_deleted(self, svc, db_session):
        await self._setup_tokens(db_session, ["user-key-1"])
        await self._setup_proxy_models(
            db_session, {"mid-active": "active-model"})
        r1 = self._row("m1", "alice", "old-name", tokens=100, spend=0.01,
                        model_id="mid-active", api_key="user-key-1")
        r2 = self._row("m2", "alice", "deleted-name", tokens=200, spend=0.02,
                        model_id="mid-gone", api_key="user-key-1")
        await self._setup_table(db_session, [r1, r2])

        result = await svc.get_usage_by_model(
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 2))
        models = [i["model"] for i in result["items"]]
        assert "active-model" in models
        assert "已删除模型" in models

    # [场景] 系统内部 key（health-check、master-key、None）的记录不应计入统计
    # [预期] 只有真实用户 key 的记录被统计
    async def test_user_traffic_filter_excludes_system_keys(self, svc, db_session):
        await self._setup_tokens(db_session, ["user-key-1"])
        await self._setup_table(db_session, [
            self._row("r1", "alice", "gpt-4", tokens=100,
                      api_key="user-key-1"),
            self._row("r2", "", "qwen", tokens=999,
                      api_key="litellm-internal-health-check"),
            self._row("r3", "admin", "gpt-4", tokens=888,
                      api_key="litellm_proxy_master_key"),
        ])

        result = await svc.get_usage_overview(
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 2))
        total = sum(u["total_requests"] for u in result["users"])
        assert total == 1  # 只有 r1 被统计

    # [场景] 按天+模型分组查询趋势（管理员全局视图）
    # [预期] items 含日期+模型名，模型名从 ProxyModelTable 映射
    async def test_get_model_trend(self, svc, db_session):
        await self._setup_tokens(db_session, ["user-key-1"])
        await self._setup_proxy_models(db_session, {"mid-gpt4": "gpt-4"})
        r1 = self._row("t1", "alice", "gpt-4", tokens=100,
                        model_id="mid-gpt4", model_group="gpt-4",
                        ts="2026-07-01 10:00:00")
        r2 = self._row("t2", "alice", "gpt-4", tokens=200,
                        model_id="mid-gpt4", model_group="gpt-4",
                        ts="2026-07-02 14:00:00")
        await self._setup_table(db_session, [r1, r2])

        result = await svc.get_model_trend(
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 2))
        assert len(result["items"]) >= 1
        for item in result["items"]:
            assert item["model"] == "gpt-4"

    # [场景] 用户已删除（key 不在任何 token 表中），历史调用数据仍应统计
    # [预期] 黑名单方式不过滤已删用户的记录，只要 user 非空就统计
    async def test_deleted_token_still_counted(self, svc, db_session):
        await self._setup_tokens(db_session, ["user-key-1"])
        await self._setup_table(db_session, [
            self._row("r1", "alice", "gpt-4", tokens=100,
                      api_key="user-key-1"),
            # r2 的 key 已不在任何 token 表（用户被删），但 user 非空
            self._row("r2", "bob", "gpt-4", tokens=200,
                      api_key="user-key-deleted"),
        ])

        result = await svc.get_usage_overview(
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 2))
        total = sum(u["total_requests"] for u in result["users"])
        assert total == 2  # 两条都计入

    # [场景] 指定用户的模型趋势（个人视图）
    # [预期] 只返回该用户的数据
    async def test_get_user_model_trend(self, svc, db_session):
        await self._setup_tokens(db_session, ["user-key-1", "user-key-2"])
        await self._setup_proxy_models(
            db_session, {"mid-gpt4": "gpt-4", "mid-ds": "deepseek"})
        r1 = self._row("t1", "alice", "gpt-4", tokens=100,
                        model_id="mid-gpt4", model_group="gpt-4",
                        api_key="user-key-1")
        r2 = self._row("t2", "bob", "deepseek", tokens=200,
                        model_id="mid-ds", model_group="deepseek",
                        api_key="user-key-2")
        await self._setup_table(db_session, [r1, r2])

        result = await svc.get_user_model_trend(
            user_id="alice",
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 2),
        )
        assert len(result["items"]) == 1
        assert result["items"][0]["model"] == "gpt-4"

    # [场景] 3 个用户不同 token 用量，取 Top 2
    # [预期] items 长度 2，token 最多的排第一（按 token 降序）
    async def test_get_usage_by_user(self, svc, db_session):
        await self._setup_tokens(db_session,
            ["user-key-1", "user-key-2", "user-key-3"])
        await self._setup_table(db_session, [
            self._row("u1", "alice", "gpt-4", tokens=100,
                      api_key="user-key-1"),
            self._row("u2a", "bob", "deepseek", tokens=300,
                      api_key="user-key-2", ts="2026-07-01 11:00:00"),
            self._row("u2b", "bob", "deepseek", tokens=200,
                      api_key="user-key-2", ts="2026-07-01 12:00:00"),
            self._row("u3", "charlie", "qwen", tokens=200,
                      api_key="user-key-3", ts="2026-07-01 12:00:00"),
        ])

        result = await svc.get_usage_by_user(
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 2), top=2,
        )
        assert len(result["items"]) == 2
        assert result["items"][0]["user_id"] == "bob"  # bob token 最多（500）

    # [场景] Token 用量与消费排序不一致：alice Token 多但消费低，bob Token 少但消费高
    # [预期] 排行按 Token 用量降序（用量），alice 排第一，且 tokens 列单调递减
    async def test_get_usage_by_user_orders_by_tokens(self, svc, db_session):
        await self._setup_table(db_session, [
            self._row("r1", "alice", "deepseek", tokens=1000, spend=0.01, ts="2026-07-01 10:00:00"),
            self._row("r2", "bob", "gpt-4", tokens=500, spend=0.05, ts="2026-07-01 11:00:00"),
            self._row("r3", "charlie", "qwen", tokens=200, spend=0.02, ts="2026-07-01 12:00:00"),
        ])

        result = await svc.get_usage_by_user(
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 2), top=3,
        )
        assert [item["user_id"] for item in result["items"]] == ["alice", "bob", "charlie"]
        tokens = [item["tokens"] for item in result["items"]]
        assert tokens == sorted(tokens, reverse=True)

    # [场景] 查询 alice 的每日用量（2 天数据 + bob 干扰数据）
    # [预期] daily_activity 长度 2，user_id == "alice"
    async def test_get_user_usage(self, svc, db_session):
        await self._setup_tokens(db_session, ["user-key-1", "user-key-2"])
        await self._setup_table(db_session, [
            self._row("d1", "alice", "gpt-4", tokens=150,
                      ts="2026-07-01 08:00:00", api_key="user-key-1"),
            self._row("d2", "alice", "deepseek", tokens=200,
                      ts="2026-07-01 16:00:00", api_key="user-key-1"),
            self._row("d3", "alice", "qwen", tokens=300,
                      ts="2026-07-02 10:00:00", api_key="user-key-1"),
            self._row("d4", "bob", "gpt-4", tokens=999,
                      ts="2026-07-01 12:00:00", api_key="user-key-2"),
        ])

        result = await svc.get_user_usage(
            user_id="alice",
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 2),
        )
        assert result["user_id"] == "alice"
        assert len(result["daily_activity"]) == 2

    # [场景] 用户有 2 成功 + 1 失败，共 3 次调用
    # [预期] success_rate == 66.7
    async def test_get_user_usage_success_rate(self, svc, db_session):
        await self._setup_tokens(db_session, ["user-key-1"])
        await self._setup_table(db_session, [
            self._row("s1", "alice", "gpt-4", status="success",
                      api_key="user-key-1"),
            self._row("s2", "alice", "gpt-4", status="success",
                      api_key="user-key-1"),
            self._row("s3", "alice", "gpt-4", status="failure",
                      api_key="user-key-1"),
        ])

        result = await svc.get_user_usage(
            user_id="alice",
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 2),
        )
        assert result["success_rate"] == 66.7

    # [场景] 查询 2 天跨度的全部用户总览，3 条数据覆盖 alice + bob
    # [预期] users 长度 2，daily 长度 2，success_rate 正确
    async def test_get_usage_overview(self, svc, db_session):
        await self._setup_tokens(db_session, ["user-key-1", "user-key-2"])
        r1 = self._row("o1", "alice", "gpt-4", tokens=100,
                        ts="2026-07-01 10:00:00", status="success",
                        api_key="user-key-1")
        r2 = self._row("o2", "bob", "deepseek", tokens=200,
                        ts="2026-07-01 14:00:00", status="success",
                        api_key="user-key-2")
        r3 = self._row("o3", "alice", "qwen", tokens=300,
                        ts="2026-07-02 09:00:00", status="failure",
                        api_key="user-key-1")
        await self._setup_table(db_session, [r1, r2, r3])

        result = await svc.get_usage_overview(
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 2))
        assert len(result["users"]) == 2
        assert len(result["daily"]) == 2
        assert result["daily"][0]["active_users"] == 2
        assert result["daily"][1]["active_users"] == 1
        assert result["success_rate"] == 66.7  # 2 success / 3 total

    # [场景] spend 表不存在时调用 get_usage_trend（触发表不存在的 ProgrammingError）
    # [预期] 返回空 items，不抛异常（优雅降级）
    async def test_spend_table_not_exists_graceful(self, svc, db_session):
        await db_session.execute(
            text('DROP TABLE IF EXISTS "LiteLLM_SpendLogs"'))
        await db_session.commit()

        result = await svc.get_usage_trend(
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 2),
        )
        assert result["items"] == []

    # [场景] DB 连接异常（非 ProgrammingError）时调用 _query_spend
    # [预期] 异常向上传播，不被吞掉
    async def test_spend_query_connection_error_propagates(self, svc, db_session):
        with patch.object(svc, '_get_spend_session', return_value=db_session):
            with patch.object(
                db_session, "execute",
                side_effect=OSError("Connection refused"),
            ):
                with pytest.raises(OSError, match="Connection refused"):
                    await svc.get_usage_trend(
                        start_date=date(2026, 7, 1),
                        end_date=date(2026, 7, 2),
                    )
