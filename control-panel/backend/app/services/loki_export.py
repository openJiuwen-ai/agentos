from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import AsyncIterator

import httpx

from app.config import settings

LOKI_BASE = "http://loki:8096/loki/api/v1"

_EPOCH = datetime.fromtimestamp(0, tz=timezone.utc)


class LokiQueryClient:
    """Loki HTTP API 轻量封装。"""

    def __init__(self, base_url: str | None = None):
        self._base = (base_url or settings.LOKI_BASE_URL).rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        limit: int = 5000,
        direction: str = "backward",
    ) -> dict:
        client = await self._get_client()
        resp = await client.get(
            f"{self._base}/query_range",
            params={
                "query": query,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": limit,
                "direction": direction,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def query_instant(
        self,
        query: str,
        limit: int = 100,
    ) -> dict:
        client = await self._get_client()
        resp = await client.get(
            f"{self._base}/query",
            params={
                "query": query,
                "limit": limit,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def labels(self) -> list[str]:
        client = await self._get_client()
        resp = await client.get(f"{self._base}/labels")
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    async def label_values(self, label: str, query: str | None = None) -> list[str]:
        """获取标签值，可选传入 LogQL 选择器（query）过滤。"""
        client = await self._get_client()
        params: dict[str, str] = {}
        if query:
            params["query"] = query
        resp = await client.get(f"{self._base}/label/{label}/values", params=params)
        if resp.status_code == httpx.codes.NOT_FOUND:
            return []
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    async def tail(
        self,
        query: str,
    ) -> AsyncIterator[dict]:
        client = await self._get_client()
        async with client.stream(
            "GET",
            f"{self._base}/tail",
            params={"query": query},
            timeout=None,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line:
                    import json

                    yield json.loads(line)


@dataclass(frozen=True)
class LokiPagedQuery:
    """一次分页拉取所需的全部参数。"""

    client: LokiQueryClient
    query: str
    start: datetime
    end: datetime
    limit: int = 5000
    max_pages: int = 2000


async def query_range_pages(
    params: LokiPagedQuery,
) -> AsyncIterator[list[tuple[int, str]]]:
    """分页拉取 query_range 结果，返回 (纳秒时间戳, 日志行) 列表，整体按时间降序。

    Loki 单次查询最多返回 limit 条，这里以每页最早一条的时间戳作为下一页的
    end 继续向前翻页，并用 seen 集合去重边界重叠，直到 start 或没有更多数据。
    """
    start_ns = int(params.start.timestamp() * 1e9)
    current_end = params.end
    seen: set[tuple[int, str]] = set()

    for _ in range(params.max_pages):
        data = await params.client.query_range(
            query=params.query,
            start=params.start,
            end=current_end,
            limit=params.limit,
            direction="backward",
        )
        results = data.get("data", {}).get("result", [])
        total = 0
        batch: list[tuple[int, str]] = []
        min_ts: int | None = None
        for stream in results:
            for ts_str, line in stream.get("values", []):
                total += 1
                try:
                    ts = int(ts_str)
                except (TypeError, ValueError):
                    continue
                if ts < start_ns:
                    continue
                key = (ts, line)
                if key in seen:
                    continue
                seen.add(key)
                batch.append((ts, line))
                if min_ts is None or ts < min_ts:
                    min_ts = ts
        if batch:
            yield batch
        if total < params.limit or min_ts is None or min_ts <= start_ns:
            return
        current_end = _EPOCH + timedelta(microseconds=min_ts // 1000)

    raise RuntimeError("Loki 查询分页数超过上限，导出可能不完整")
