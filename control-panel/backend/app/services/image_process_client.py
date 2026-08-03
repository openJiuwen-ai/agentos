"""HTTP client for the standalone image_process service."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class ImageProcessError(Exception):
    """Raised when image_process is unreachable or rejects a build request."""


@dataclass(frozen=True)
class RemoteBuildStatus:
    """Subset of image_process GET /v1/builds/{id} used for DB sync."""

    status: str
    progress: int = 0
    image: str | None = None
    image_digest: str | None = None
    image_path: str | None = None
    base_image: str | None = None
    error_message: str | None = None


def _base_url() -> str:
    base = (settings.IMAGE_PROCESS_URL or "").rstrip("/")
    if not base:
        raise ImageProcessError("IMAGE_PROCESS_URL is not configured")
    return base


async def submit_build(
    *,
    task_id: str,
    agent_name: str,
    version: str,
    installer_path: str,
    output_dir: str,
    work_dir: str | None = None,
) -> None:
    """Enqueue a build on image_process. Raises ImageProcessError on failure."""
    url = f"{_base_url()}/v1/builds"
    payload = {
        "task_id": task_id,
        "agent_name": agent_name,
        "version": version,
        "installer_path": installer_path,
        "output_dir": output_dir,
        "work_dir": work_dir,
    }
    timeout = settings.IMAGE_PROCESS_TIMEOUT_SECONDS
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
    except httpx.TimeoutException as e:
        raise ImageProcessError(f"image_process timeout: {url}") from e
    except httpx.HTTPError as e:
        raise ImageProcessError(f"image_process unreachable: {e}") from e

    if resp.status_code >= 400:
        detail = resp.text[:500]
        raise ImageProcessError(
            f"image_process rejected build ({resp.status_code}): {detail}"
        )
    logger.info("build submitted to image_process task=%s", task_id)


async def fetch_build(task_id: str) -> RemoteBuildStatus | None:
    """Poll image_process for task status.

    Returns ``None`` when the remote task is missing (404) or temporarily
    unreachable — caller keeps the local DB snapshot.
    """
    try:
        url = f"{_base_url()}/v1/builds/{task_id}"
    except ImageProcessError:
        logger.warning("fetch_build skipped task=%s: IMAGE_PROCESS_URL not configured", task_id)
        return None

    timeout = settings.IMAGE_PROCESS_TIMEOUT_SECONDS
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
    except httpx.HTTPError as e:
        logger.warning("fetch_build unreachable task=%s: %s", task_id, e)
        return None

    if resp.status_code == 404:
        return None
    if resp.status_code >= 400:
        logger.warning(
            "fetch_build rejected task=%s status=%s body=%s",
            task_id, resp.status_code, resp.text[:300],
        )
        return None

    body = resp.json()
    return RemoteBuildStatus(
        status=body.get("status") or "pending",
        progress=int(body.get("progress") or 0),
        image=body.get("image"),
        image_digest=body.get("image_digest"),
        image_path=body.get("image_path"),
        base_image=body.get("base_image"),
        error_message=body.get("error_message"),
    )
