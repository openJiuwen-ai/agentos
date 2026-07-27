"""agent_snapshot 单元 + 服务层 + 路由测试 —— 实例监控快照服务。

覆盖：版本号排序、状态/关键词匹配、概览计数、查询(搜索/筛选/排序/分页)、
注册中心未配置守卫(503)、ensure_snapshot 装载、路由 max_length 校验。

隔离：所有网络经 mock；模块级 _snapshot/_overview/_lock 由 autouse fixture 还原；
settings 经 monkeypatch 自动还原。不影响其他用例。
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.services import agent_snapshot
from app.services.agent_snapshot import (
    SnapshotQuery,
    AgentRegisterNotConfiguredError,
    _compute_overview,
    _fetch_from_registry,
    _match_keyword,
    _match_status,
    _version_key,
    ensure_snapshot,
    query,
    total_pages,
)

# ── 测试数据 ──
SAMPLE: list[dict] = [
    {
        "service_id": "svc-1",
        "framework": "langgraph",
        "framework_version": "v1.10.0",
        "status": "运行",
        "user": "alice",
        "address": "10.0.0.1:8080",
        "node": "node-a",
        "created_at": "2026-07-01T00:00:00Z",
        "last_active_at": "2026-07-10T00:00:00Z",
    },
    {
        "service_id": "svc-2",
        "framework": "autogen",
        "framework_version": "v1.4.0",
        "status": "异常",
        "user": "bob",
        "address": "10.0.0.2:8080",
        "node": "node-b",
        "created_at": "2026-07-02T00:00:00Z",
        "last_active_at": None,
    },
    {
        "service_id": "svc-3",
        "framework": "langgraph",
        "framework_version": "v0.9.8",
        "status": None,
        "user": "alice",
        "address": "10.0.0.3:8080",
        "node": "node-a",
        "created_at": "2026-07-03T00:00:00Z",
        "last_active_at": None,
    },
]


@pytest.fixture(autouse=True)
def _reset_snapshot_state():
    """保存/还原模块级全局，防止用例间泄漏。"""
    saved = (
        getattr(agent_snapshot, "_snapshot"),
        getattr(agent_snapshot, "_overview"),
        getattr(agent_snapshot, "_lock"),
    )
    yield
    setattr(agent_snapshot, "_snapshot", saved[0])
    setattr(agent_snapshot, "_overview", saved[1])
    setattr(agent_snapshot, "_lock", saved[2])


# ── httpx fake（供守卫 happy-path 使用，绝不发真实请求）──


class _FakeResponse:
    def __init__(self, status_code: int, payload: list) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self) -> list:
        return self._payload


def _fake_async_client(response: _FakeResponse):
    """返回一个替换 httpx.AsyncClient 的工厂。"""

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, params=None):
            return response

    return lambda *a, **kw: _Client()


def _load_sample():
    """把 SAMPLE 装入模块级快照 + 概览。"""
    setattr(agent_snapshot, "_snapshot", list(SAMPLE))
    setattr(agent_snapshot, "_overview", _compute_overview(SAMPLE))


# ── 纯单元测试 ─────────────────────────────────────────────────────────────


class TestVersionKey:
    @staticmethod
    def test_multi_digit_version_orders_correctly():
        # 字典序会误判 v1.10.0 < v1.4.0；_version_key 应正确排序
        versions = ["v1.10.0", "v1.4.0", "v0.9.8", "v2.0.0"]
        assert sorted(versions, key=_version_key) == [
            "v0.9.8",
            "v1.4.0",
            "v1.10.0",
            "v2.0.0",
        ]

    @staticmethod
    def test_v_prefix_and_leading_zeros_normalized():
        assert _version_key("v01.02") == _version_key("1.2")

    @staticmethod
    def test_non_numeric_falls_to_group1():
        # 纯文本归入第 1 组，排在数字版本之后
        assert _version_key("v1.0.0")[0][0] == 0
        assert _version_key("latest")[0][0] == 1


class TestMatchStatus:
    @staticmethod
    def test_none_matches_stopped_sentinel():
        assert _match_status({"status": None}, ["stopped"]) is True
        assert _match_status({"status": None}, ["运行"]) is False

    @staticmethod
    def test_chinese_status_direct_match():
        assert _match_status({"status": "运行"}, ["运行", "异常"]) is True
        assert _match_status({"status": "异常"}, ["stopped"]) is False


class TestComputeOverview:
    @staticmethod
    def test_counts():
        assert _compute_overview(SAMPLE) == {
            "total": 3,
            "running": 1,
            "abnormal": 1,
            "stopped": 1,
        }


class TestMatchKeyword:
    @staticmethod
    def test_partial_case_insensitive():
        # kw_lower 需调用方预先小写（见 query() 中 kw.lower()）
        assert _match_keyword({"service_id": "Svc-Alpha"}, "svc-al") is True
        assert _match_keyword({"user": "Alice"}, "ali") is True

    @staticmethod
    def test_no_match():
        assert _match_keyword({"service_id": "svc-1"}, "zzz") is False
        assert _match_keyword({}, "x") is False


class TestQuery:
    @staticmethod
    def test_framework_version_sort_asc_desc():
        _load_sample()
        asc, _, _ = query(SnapshotQuery(page=1, size=10, sort="framework_version:asc"))
        assert [i["framework_version"] for i in asc] == [
            "v0.9.8",
            "v1.4.0",
            "v1.10.0",
        ]
        desc, _, _ = query(SnapshotQuery(page=1, size=10, sort="framework_version:desc"))
        assert [i["framework_version"] for i in desc] == [
            "v1.10.0",
            "v1.4.0",
            "v0.9.8",
        ]

    @staticmethod
    def test_sort_nulls_last():
        _load_sample()
        items, _, _ = query(SnapshotQuery(page=1, size=10, sort="last_active_at:asc"))
        non_null = [i for i in items if i["last_active_at"] is not None]
        nulls = [i for i in items if i["last_active_at"] is None]
        assert items[:len(non_null)] == non_null
        assert items[len(non_null):] == nulls

    @staticmethod
    def test_keyword_search():
        _load_sample()
        items, total, _ = query(SnapshotQuery(page=1, size=10, keyword="alice"))
        assert total == 2
        assert all(i["user"] == "alice" for i in items)

    @staticmethod
    def test_status_filter_sentinel():
        _load_sample()
        items, total, _ = query(SnapshotQuery(page=1, size=10, status="stopped"))
        assert total == 1
        assert items[0]["status"] is None

    @staticmethod
    def test_framework_filter():
        _load_sample()
        _, total, _ = query(SnapshotQuery(page=1, size=10, framework="langgraph"))
        assert total == 2

    @staticmethod
    def test_pagination_and_overview_unaffected_by_filter():
        _load_sample()
        items, total, ov = query(
            SnapshotQuery(page=1, size=1, framework="langgraph")
        )
        assert len(items) == 1
        assert total == 2
        assert ov == {"total": 3, "running": 1, "abnormal": 1, "stopped": 1}

    @staticmethod
    def test_empty_page_when_beyond_total():
        _load_sample()
        items, total, _ = query(SnapshotQuery(page=5, size=10))
        assert items == []
        assert total == 3


class TestTotalPages:
    @staticmethod
    def test_zero_returns_one():
        assert total_pages(0, 10) == 1

    @staticmethod
    def test_ceil_and_size_fallback():
        assert total_pages(11, 10) == 2
        assert total_pages(3, 0) == 1  # size<=0 兜底为 10 -> ceil(3/10)=1


# ── 服务层：注册中心未配置守卫 + 装载 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_disabled_raises_not_configured(monkeypatch):
    """AGENT_REGISTER_URL 为空 → _fetch_from_registry 抛 503。"""
    monkeypatch.setattr(settings, "AGENT_REGISTER_URL", "")
    with pytest.raises(AgentRegisterNotConfiguredError) as ei:
        await _fetch_from_registry()
    assert ei.value.status_code == 503


@pytest.mark.asyncio
async def test_fetch_enabled_returns_data(monkeypatch):
    """已配置 + mock httpx → 守卫放行并返回数据。"""
    monkeypatch.setattr(settings, "AGENT_REGISTER_URL", "http://agent-register.test")
    monkeypatch.setattr(
        agent_snapshot.httpx,
        "AsyncClient",
        _fake_async_client(_FakeResponse(200, SAMPLE)),
    )
    assert await _fetch_from_registry() == SAMPLE


@pytest.mark.asyncio
async def test_ensure_snapshot_loads_into_globals(monkeypatch):
    """ensure_snapshot 把数据装入模块级 _snapshot/_overview。"""
    monkeypatch.setattr(settings, "AGENT_REGISTER_URL", "http://agent-register.test")
    monkeypatch.setattr(
        agent_snapshot.httpx,
        "AsyncClient",
        _fake_async_client(_FakeResponse(200, SAMPLE)),
    )
    assert getattr(agent_snapshot, "_snapshot") is None
    await ensure_snapshot()
    assert getattr(agent_snapshot, "_snapshot") == SAMPLE
    assert getattr(agent_snapshot, "_overview") == {
        "total": 3,
        "running": 1,
        "abnormal": 1,
        "stopped": 1,
    }


# ── 路由层：max_length 校验 + 未配置 503 ──────────────────────────────────


@pytest.mark.asyncio
async def test_route_max_length_rejects_overlimit(client, admin_tokens, monkeypatch):
    """超长查询参数 → 422（handler 不执行，不触达注册中心）。"""
    monkeypatch.setattr(settings, "AGENT_REGISTER_URL", "")
    headers = {"Authorization": f"Bearer {admin_tokens['access_token']}"}
    for param, n in [("keyword", 501), ("sort", 101), ("status", 101), ("framework", 201)]:
        resp = await client.get(
            "/api/v1/agent/instances",
            params={param: "a" * n},
            headers=headers,
        )
        assert resp.status_code == 422, f"{param} len={n} 应为 422"


@pytest.mark.asyncio
async def test_route_not_configured_returns_503(client, admin_tokens, monkeypatch):
    """未配置注册中心 → 503 + 固定 detail。"""
    monkeypatch.setattr(settings, "AGENT_REGISTER_URL", "")
    resp = await client.get(
        "/api/v1/agent/instances",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "注册中心服务未配置，智能体监控不可用"
