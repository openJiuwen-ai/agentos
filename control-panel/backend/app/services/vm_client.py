"""VictoriaMetrics instant query client."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VmSample:
    metric: dict[str, str]
    value: float


class VmClient:
    """Read-only VictoriaMetrics /api/v1/query client."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    @property
    def configured(self) -> bool:
        return bool(self._base_url)

    async def is_available(self) -> bool:
        if not self.configured:
            return False
        try:
            resp = await self._client.get(
                f"{self._base_url}/api/v1/query",
                params={"query": "1"},
            )
            resp.raise_for_status()
            payload = resp.json()
            return payload.get("status") == "success"
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("VictoriaMetrics unavailable at %s: %s", self._base_url, exc)
            return False

    async def query(self, promql: str) -> list[VmSample]:
        if not self.configured:
            return []
        try:
            resp = await self._client.get(
                f"{self._base_url}/api/v1/query",
                params={"query": promql},
            )
            resp.raise_for_status()
            payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("VictoriaMetrics query failed: %s", exc)
            return []

        if payload.get("status") != "success":
            return []

        data = payload.get("data") or {}
        if data.get("resultType") != "vector":
            return []

        samples: list[VmSample] = []
        for item in data.get("result") or []:
            metric = item.get("metric") or {}
            raw_value = item.get("value")
            if not isinstance(raw_value, list) or len(raw_value) < 2:
                continue
            try:
                value = float(raw_value[1])
            except (TypeError, ValueError):
                continue
            samples.append(VmSample(metric=metric, value=value))
        return samples
