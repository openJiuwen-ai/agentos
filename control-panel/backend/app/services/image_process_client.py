"""HTTP client for the standalone image_process factory."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class ImageProcessError(Exception):
    """Raised when image_process is unreachable or rejects a request."""


def _json_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


@dataclass
class RemoteBuildStatus:
    status: str
    progress: int = 0
    name: str | None = None
    version: str | None = None
    image_ref: str | None = None
    archive_path: str | None = None
    runtime_spec: dict | None = None
    recipe_id: str | None = None
    base_ref: str | None = None
    image_digest: str | None = None
    image_module_version: str | None = None
    error_message: str | None = None


class ImageProcessClient:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._client = client
        self._base_url = (
            base_url if base_url is not None else settings.IMAGE_PROCESS_URL
        ).rstrip("/")
        self._timeout = (
            timeout if timeout is not None else settings.IMAGE_PROCESS_TIMEOUT_SECONDS
        )

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if self._client is not None:
            return await self._client.request(
                method, url, timeout=self._timeout, **kwargs
            )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.request(method, url, **kwargs)

    def _require_url(self) -> str:
        if not self._base_url:
            raise ImageProcessError("IMAGE_PROCESS_URL is not configured")
        return self._base_url

    async def build_from_path(
        self,
        package_path: str,
        request_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        url = f"{self._require_url()}/v1/builds"
        payload: dict[str, Any] = {"package_path": package_path}
        if request_id:
            payload["request_id"] = request_id
        if options:
            payload["options"] = options
        try:
            resp = await self._request("POST", url, json=payload)
        except httpx.TimeoutException as e:
            raise ImageProcessError(f"image_process timeout: {url}") from e
        except httpx.HTTPError as e:
            raise ImageProcessError(f"image_process unreachable: {e}") from e
        if resp.status_code >= 400:
            raise ImageProcessError(
                f"image_process rejected build ({resp.status_code}): {resp.text[:500]}"
            )
        data = _json_body(resp) or {}
        rid = data.get("request_id") or request_id
        if not rid:
            raise ImageProcessError("image_process did not return request_id")
        logger.info("build submitted to image_process request=%s", rid)
        return str(rid)

    async def fetch_build(self, request_id: str) -> RemoteBuildStatus | None:
        url = f"{self._require_url()}/v1/builds/{request_id}"
        try:
            resp = await self._request("GET", url)
        except httpx.HTTPError:
            return None
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            return None
        data = _json_body(resp) or {}
        return RemoteBuildStatus(
            status=data.get("status") or "pending",
            progress=int(data.get("progress") or 0),
            name=data.get("name"),
            version=data.get("version"),
            image_ref=data.get("image_ref"),
            archive_path=data.get("archive_path"),
            runtime_spec=data.get("runtime_spec"),
            recipe_id=data.get("recipe_id"),
            base_ref=data.get("base_ref"),
            image_digest=data.get("image_digest"),
            image_module_version=data.get("image_module_version"),
            error_message=data.get("error_message"),
        )

    async def remove_loaded_image(self, tag: str) -> None:
        url = f"{self._require_url()}/v1/images/remove"
        try:
            resp = await self._request(
                "POST",
                url,
                json={"tag": tag},
            )
        except httpx.TimeoutException as e:
            raise ImageProcessError(f"image_process timeout: {url}") from e
        except httpx.HTTPError as e:
            raise ImageProcessError(f"image_process unreachable: {e}") from e
        if resp.status_code >= 400:
            raise ImageProcessError(
                f"image_process rejected remove ({resp.status_code}): {resp.text[:500]}"
            )
