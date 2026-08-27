"""Loki 导出分页查询单元测试。"""

from datetime import datetime, timedelta, timezone

from app.services.loki_export import LokiPagedQuery, query_range_pages

_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
_END = datetime(2026, 1, 2, tzinfo=timezone.utc)
_START_NS = int(_START.timestamp() * 1e9)
_END_NS = int(_END.timestamp() * 1e9)


def _page(*rows):
    """构造一页 Loki query_range 响应。rows 为 (纳秒时间戳, 日志行)。"""
    return {
        "data": {
            "result": [
                {"stream": {}, "values": [[str(ts), line] for ts, line in rows]}
            ]
        }
    }


class _FakeLokiClient:
    """按调用顺序返回预置页面的假 Loki 客户端。"""

    def __init__(self, pages):
        self.pages = pages
        self.calls = 0

    async def query_range(self, query, start, end, limit, direction):
        page = self.pages[min(self.calls, len(self.pages) - 1)]
        self.calls += 1
        return page


async def test_query_range_pages_continues_when_page_is_full():
    """首页返回达到 limit 时，应继续翻页而不是报错（回归：limit 未定义）。"""
    client = _FakeLokiClient([
        # 首页 3 条，超过 limit=2，应触发继续翻页
        _page(
            (_END_NS, "line1"),
            (_END_NS - 1, "line2"),
            (_END_NS - 2, "line3"),
        ),
        # 第二页 1 条，少于 limit，应停止
        _page((_END_NS - 3, "line4")),
    ])
    params = LokiPagedQuery(
        client=client,  # type: ignore[arg-type]
        query='{job="test"}',
        start=_START,
        end=_END,
        limit=2,
        max_pages=10,
    )

    batches = [batch async for batch in query_range_pages(params)]
    lines = [line for batch in batches for _, line in batch]

    assert client.calls == 2
    assert len(batches) == 2
    assert lines == ["line1", "line2", "line3", "line4"]


async def test_query_range_pages_stops_when_page_not_full():
    """首页返回少于 limit 时，应只取一页就结束。"""
    client = _FakeLokiClient([
        _page((_END_NS, "line1")),
    ])
    params = LokiPagedQuery(
        client=client,  # type: ignore[arg-type]
        query='{job="test"}',
        start=_START,
        end=_END,
        limit=5000,
        max_pages=10,
    )

    batches = [batch async for batch in query_range_pages(params)]
    lines = [line for batch in batches for _, line in batch]

    assert client.calls == 1
    assert len(batches) == 1
    assert lines == ["line1"]
