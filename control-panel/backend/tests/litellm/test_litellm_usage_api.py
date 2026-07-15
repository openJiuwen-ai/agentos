"""测试使用统计 API 端点 — 5 个端点

每个用例的注释格式：
  [场景] 描述了什么样的输入条件和操作上下文
  [预期] 期望的 HTTP 状态码和响应数据
"""

from unittest.mock import AsyncMock, patch

import pytest


class TestUsageTrendAPI:
    """GET /api/v1/litellm/usage/trend — Token/请求数/成本趋势图"""

    # [场景] 查询 7 月 1~2 日的趋势，mock 返回 1 条数据
    # [预期] HTTP 200，data.granularity == "day"，items 长度 1
    async def test_trend_day(self, client):
        mock_data = {
            "start_date": "2026-07-01",
            "end_date": "2026-07-02",
            "granularity": "day",
            "items": [
                {"time": "2026-07-01T00:00:00Z", "tokens": 1500, "requests": 30, "cost": 0.015},
            ],
        }
        with patch(
            "app.api.v1.litellm_usage.LitellmService.get_usage_trend",
            new=AsyncMock(return_value=mock_data),
        ):
            resp = await client.get(
                "/api/v1/litellm/usage/trend?start_date=2026-07-01&end_date=2026-07-02&granularity=day"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["data"]["granularity"] == "day"
            assert len(data["data"]["items"]) == 1

    # [场景] 按用户 alice 过滤趋势，验证 user_id 参数透传到服务层
    # [预期] HTTP 200，mock 方法收到 user_id="alice"（需 admin 角色才能透传）
    async def test_trend_with_user_filter(self, client):
        """admin 角色下 user_id 参数透传到 service 层"""
        from app.main import app as _app
        from app.iam.deps import get_current_user
        from app.iam.tokens import TokenData

        old_user = _app.dependency_overrides.get(get_current_user)

        async def _admin():
            return TokenData(user_id="admin-001", username="admin", role="admin")
        _app.dependency_overrides[get_current_user] = _admin

        try:
            mock_data = {
                "start_date": "2026-07-01",
                "end_date": "2026-07-02",
                "granularity": "day",
                "items": [],
            }
            with patch(
                "app.api.v1.litellm_usage.LitellmService.get_usage_trend",
                new=AsyncMock(return_value=mock_data),
            ) as mock_method:
                await client.get(
                    "/api/v1/litellm/usage/trend?start_date=2026-07-01&end_date=2026-07-02&user_id=alice"
                )
                call_kwargs = mock_method.call_args.kwargs
                assert call_kwargs["user_id"] == "alice"
        finally:
            if old_user:
                _app.dependency_overrides[get_current_user] = old_user

    # [场景] 传入非法的 granularity 参数（hour、week、year、空字符串）
    # [预期] HTTP 422
    @pytest.mark.parametrize("bad_granularity", ["hour", "week", "year", ""])
    async def test_trend_invalid_granularity_422(self, client, bad_granularity):
        resp = await client.get(
            "/api/v1/litellm/usage/trend"
            f"?start_date=2026-07-01&end_date=2026-07-02&granularity={bad_granularity}"
        )
        assert resp.status_code == 422


class TestUsageByModelAPI:
    """GET /api/v1/litellm/usage/by-model — 模型用量分布"""

    # [场景] mock 返回两部模型的用量分布（deepseek-chat 53.3%, gpt-4o 33.3%）
    # [预期] HTTP 200，items 长度 2，第一项 pct == 53.3
    async def test_by_model(self, client):
        mock_data = {
            "items": [
                {"model": "deepseek-chat", "tokens": 80000, "requests": 1600, "cost": 0.80, "pct": 53.3},
                {"model": "gpt-4o", "tokens": 50000, "requests": 1000, "cost": 0.50, "pct": 33.3},
            ],
        }
        with patch(
            "app.api.v1.litellm_usage.LitellmService.get_usage_by_model",
            new=AsyncMock(return_value=mock_data),
        ):
            resp = await client.get(
                "/api/v1/litellm/usage/by-model?start_date=2026-07-01&end_date=2026-07-06"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["data"]["items"]) == 2
            assert data["data"]["items"][0]["pct"] == 53.3


class TestUsageByUserAPI:
    """GET /api/v1/litellm/usage/by-user — 用户用量排行"""

    # [场景] mock 返回 Top 2 用户排行，验证 top 参数传递
    # [预期] HTTP 200，items 长度 2，mock 收到 top=2
    async def test_by_user_top(self, client):
        mock_data = {
            "items": [
                {"user_id": "admin", "tokens": 80000, "requests": 1600, "cost": 0.80},
                {"user_id": "alice", "tokens": 50000, "requests": 1000, "cost": 0.50},
            ],
        }
        with patch(
            "app.api.v1.litellm_usage.LitellmService.get_usage_by_user",
            new=AsyncMock(return_value=mock_data),
        ) as mock_method:
            resp = await client.get(
                "/api/v1/litellm/usage/by-user?start_date=2026-07-01&end_date=2026-07-06&top=2"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["data"]["items"]) == 2

            call_kwargs = mock_method.call_args.kwargs
            assert call_kwargs["top"] == 2


class TestUsageUserAPI:
    """GET /api/v1/litellm/usage/user — 指定用户每日活动"""

    # [场景] 查询 admin 用户 7 月 1~2 日的每日活动
    # [预期] HTTP 200，daily_activity 长度为 2
    async def test_user_daily_activity(self, client):
        mock_data = {
            "user_id": "admin",
            "start_date": "2026-07-01",
            "end_date": "2026-07-02",
            "daily_activity": [
                {"date": "2026-07-01", "tokens": 15000, "requests": 320, "cost": 0.15},
                {"date": "2026-07-02", "tokens": 22000, "requests": 450, "cost": 0.22},
            ],
        }
        with patch(
            "app.api.v1.litellm_usage.LitellmService.get_user_usage",
            new=AsyncMock(return_value=mock_data),
        ):
            resp = await client.get(
                "/api/v1/litellm/usage/user?user_id=admin&start_date=2026-07-01&end_date=2026-07-02"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["data"]["daily_activity"]) == 2


class TestUsageOverviewAPI:
    """GET /api/v1/litellm/usage/overview — 全部用户总览"""

    # [场景] mock 返回 1 个用户汇总 + 1 天趋势
    # [预期] HTTP 200，users 长度 1，daily 长度 1
    async def test_overview(self, client):
        mock_data = {
            "start_date": "2026-07-01",
            "end_date": "2026-07-02",
            "users": [
                {"user_id": "admin", "total_tokens": 150000, "total_requests": 3200, "total_cost": 1.50},
            ],
            "daily": [
                {"date": "2026-07-01", "tokens": 35000, "requests": 700, "cost": 0.35},
            ],
        }
        with patch(
            "app.api.v1.litellm_usage.LitellmService.get_usage_overview",
            new=AsyncMock(return_value=mock_data),
        ):
            resp = await client.get(
                "/api/v1/litellm/usage/overview?start_date=2026-07-01&end_date=2026-07-02"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["data"]["users"]) == 1
            assert len(data["data"]["daily"]) == 1


class TestUsageDataIsolation:
    """验证非 admin 用户只能看到自己的数据"""

    @pytest.fixture(autouse=True)
    def _mock_user(self):
        """替换 get_current_user 为普通 user 角色"""
        from app.main import app as _app
        from app.iam.deps import get_current_user, require_admin, require_permission
        from app.iam.tokens import TokenData

        old_user = _app.dependency_overrides.get(get_current_user)
        old_admin = _app.dependency_overrides.get(require_admin)
        old_perm = _app.dependency_overrides.get(require_permission)

        async def _user():
            return TokenData(user_id="test-user-001", username="testuser", role="user")

        _app.dependency_overrides[get_current_user] = _user
        # 清除 admin override，让 require_admin 真实执行（user 会被拒）
        _app.dependency_overrides[require_admin] = require_admin
        _app.dependency_overrides[require_permission] = require_permission

        yield

        if old_user:
            _app.dependency_overrides[get_current_user] = old_user
        if old_admin:
            _app.dependency_overrides[require_admin] = old_admin
        if old_perm:
            _app.dependency_overrides[require_permission] = old_perm

    # [场景] 普通 user 请求 /trend 并指定 user_id=other_user
    # [预期] service 层收到的 user_id 被替换为当前用户 ID
    async def test_trend_forces_own_user_id(self, client):
        mock_data = {
            "start_date": "2026-07-01",
            "end_date": "2026-07-02",
            "granularity": "day",
            "items": [],
        }
        with patch(
            "app.api.v1.litellm_usage.LitellmService.get_usage_trend",
            new=AsyncMock(return_value=mock_data),
        ) as mock_method:
            resp = await client.get(
                "/api/v1/litellm/usage/trend"
                "?start_date=2026-07-01&end_date=2026-07-02&user_id=other_user"
            )
            assert resp.status_code == 200
            assert mock_method.call_args.kwargs["user_id"] == "test-user-001"

    # [场景] 普通 user 请求 /user 并指定 user_id=other_user
    # [预期] service 层收到的 user_id 被替换为当前用户 ID
    async def test_user_detail_forces_own_user_id(self, client):
        mock_data = {
            "user_id": "test-user-001",
            "start_date": "2026-07-01",
            "end_date": "2026-07-02",
            "daily_activity": [],
        }
        with patch(
            "app.api.v1.litellm_usage.LitellmService.get_user_usage",
            new=AsyncMock(return_value=mock_data),
        ) as mock_method:
            resp = await client.get(
                "/api/v1/litellm/usage/user"
                "?user_id=other_user&start_date=2026-07-01&end_date=2026-07-02"
            )
            assert resp.status_code == 200
            assert mock_method.call_args.kwargs["user_id"] == "test-user-001"

    # [场景] admin 请求 /trend 并指定 user_id=other_user
    # [预期] service 层收到原始 user_id，不做替换
    async def test_admin_preserves_requested_user_id(self, client):
        """恢复 admin mock 验证 admin 不受隔离影响"""
        from app.main import app as _app
        from app.iam.deps import get_current_user, require_admin, require_permission
        from app.iam.tokens import TokenData

        old_user = _app.dependency_overrides.get(get_current_user)
        old_admin = _app.dependency_overrides.get(require_admin)
        old_perm = _app.dependency_overrides.get(require_permission)

        async def _admin():
            return TokenData(user_id="admin-001", username="admin", role="admin")
        _app.dependency_overrides[get_current_user] = _admin
        _app.dependency_overrides[require_admin] = _admin
        _app.dependency_overrides[require_permission] = require_permission

        try:
            mock_data = {
                "start_date": "2026-07-01",
                "end_date": "2026-07-02",
                "granularity": "day",
                "items": [],
            }
            with patch(
                "app.api.v1.litellm_usage.LitellmService.get_usage_trend",
                new=AsyncMock(return_value=mock_data),
            ) as mock_method:
                resp = await client.get(
                    "/api/v1/litellm/usage/trend"
                    "?start_date=2026-07-01&end_date=2026-07-02&user_id=other_user"
                )
                assert resp.status_code == 200
                assert mock_method.call_args.kwargs["user_id"] == "other_user"
        finally:
            if old_user:
                _app.dependency_overrides[get_current_user] = old_user
            if old_admin:
                _app.dependency_overrides[require_admin] = old_admin
            if old_perm:
                _app.dependency_overrides[require_permission] = old_perm
