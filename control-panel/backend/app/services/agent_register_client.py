"""HTTP client for the agent registration center."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class AgentRegisterError(Exception):
    """Raised when the registration center is unreachable or rejects a call."""


def _json_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


class AgentRegisterClient:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._client = client
        raw = base_url if base_url is not None else settings.AGENT_REGISTER_URL
        self._base_url = (raw or "").rstrip("/")
        self._timeout = timeout

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if self._client is not None:
            return await self._client.request(
                method, url, timeout=self._timeout, **kwargs
            )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.request(method, url, **kwargs)

    def _require_url(self) -> str:
        if not self._base_url:
            raise AgentRegisterError("AGENT_REGISTER_URL is not configured")
        return self._base_url

    async def list_images(
        self,
        *,
        framework: str = "",
        uploaded_by: str = "",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        url = f"{self._require_url()}/api/images"
        params: dict[str, Any] = {"framework": framework, "uploaded_by": uploaded_by}
        if size > 0:
            params["page"] = page
            params["size"] = size
        try:
            resp = await self._request("GET", url, params=params)
        except httpx.HTTPError as e:
            raise AgentRegisterError(f"registry unreachable: {e}") from e
        if resp.status_code >= 400:
            raise AgentRegisterError(f"registry returned {resp.status_code}")
        body = _json_body(resp)
        items = body if isinstance(body, list) else []
        total = int(
            resp.headers.get("x-total-count")
            or resp.headers.get("X-Total-Count")
            or len(items)
        )
        return items, total

    async def register_image(self, payload: dict[str, Any]) -> str:
        url = f"{self._require_url()}/api/images"
        try:
            resp = await self._request("POST", url, json=payload)
        except httpx.HTTPError as e:
            raise AgentRegisterError(f"registry unreachable: {e}") from e
        if resp.status_code >= 400:
            raise AgentRegisterError(
                f"registry returned {resp.status_code}: {resp.text}"
            )
        body = _json_body(resp)
        body = body if isinstance(body, dict) else {}
        status = body.get("status", "")
        if status not in ("registered", "updated"):
            raise AgentRegisterError(f"registry returned unexpected status {status!r}")
        return status

    async def delete_image(self, framework: str, framework_version: str) -> None:
        url = (
            f"{self._require_url()}/api/images/"
            f"{quote(framework, safe='')}/{quote(framework_version, safe='')}"
        )
        try:
            resp = await self._request("DELETE", url)
        except httpx.HTTPError as e:
            raise AgentRegisterError(f"registry unreachable: {e}") from e
        if resp.status_code >= 400:
            raise AgentRegisterError(
                f"registry returned {resp.status_code}: {resp.text}"
            )

    async def set_default_version(
        self, framework: str, framework_version: str
    ) -> dict[str, Any]:
        url = f"{self._require_url()}/api/images/{quote(framework, safe='')}/default"
        try:
            resp = await self._request(
                "PUT",
                url,
                json={"framework_version": framework_version},
            )
        except httpx.HTTPError as e:
            raise AgentRegisterError(f"registry unreachable: {e}") from e
        if resp.status_code >= 400:
            raise AgentRegisterError(
                f"registry returned {resp.status_code}: {resp.text}"
            )
        body = _json_body(resp)
        return body if isinstance(body, dict) else {}

    async def list_instances(
        self,
        *,
        framework: str = "",
        framework_version: str = "",
        include_unhealthy: bool = True,
        kind: str = "",
        user: str = "",
        node: str = "",
    ) -> list[dict[str, Any]]:
        url = f"{self._require_url()}/api/instances"
        params: dict[str, Any] = {
            "size": -1,
            "include_unhealthy": str(include_unhealthy).lower(),
        }
        if framework:
            params["framework"] = framework
        if kind:
            params["kind"] = kind
        if user:
            params["user"] = user
        if node:
            params["node"] = node
        try:
            resp = await self._request("GET", url, params=params)
        except httpx.HTTPError as e:
            raise AgentRegisterError(f"registry unreachable: {e}") from e
        if resp.status_code >= 400:
            raise AgentRegisterError(f"registry returned {resp.status_code}")
        body = _json_body(resp)
        items = body if isinstance(body, list) else []
        if framework_version:
            items = [
                i for i in items if i.get("framework_version") == framework_version
            ]
        return items
