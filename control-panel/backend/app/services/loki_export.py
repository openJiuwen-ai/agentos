from datetime import datetime
from typing import AsyncIterator

import httpx

from app.config import settings

LOKI_BASE = "http://loki:8096/loki/api/v1"


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

    async def label_values(self, label: str) -> list[str]:
        client = await self._get_client()
        resp = await client.get(f"{self._base}/label/{label}/values")
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
