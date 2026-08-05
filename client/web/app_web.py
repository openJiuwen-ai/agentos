# Copyright (c) Huawei Technologies Co., Ltd. 2025-2026. All rights reserved.

"""AgentOS Client —— 独立前端服务器（桌面打包版）.

职责：
1. 托管 ``frontend/dist`` 静态文件（SPA 回退到 index.html）
2. 将 ``/ws`` WebSocket 双向代理到本机已运行的 jiuwenswarm 后端（默认 127.0.0.1:19000）
3. 将 ``/file-api/*`` HTTP 代理到后端

仅依赖 aiohttp，不依赖 jiuwenswarm 包，可独立 PyInstaller 打包。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from pathlib import Path

from aiohttp import ClientSession, WSMsgType, web

logger = logging.getLogger("agentos-client.web")

_DEFAULT_BACKEND = "127.0.0.1:19000"

_PROXY_EXCLUDED_REQUEST_HEADERS = frozenset(
    {"host", "content-length", "connection", "accept-encoding"}
)
_PROXY_EXCLUDED_RESPONSE_HEADERS = frozenset(
    {"transfer-encoding", "content-encoding", "connection", "content-length"}
)


def _default_dist_dir() -> Path:
    """返回前端 dist 目录（兼容开发目录与 PyInstaller 打包目录）。"""
    # 打包后：exe 同级 agentos_web_dist/ 或 _internal/agentos_web_dist/
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates = [
            exe_dir / "agentos_web_dist",
            exe_dir / "_internal" / "agentos_web_dist",
            Path(getattr(sys, "_MEIPASS", exe_dir)) / "agentos_web_dist",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]
    # 开发时：client/web/frontend/dist
    return Path(__file__).resolve().parent / "frontend" / "dist"


class WebInterface:
    """静态托管 + /ws 与 /file-api 反向代理。"""

    def __init__(self, dist_dir: Path, backend: str) -> None:
        self.dist_dir = dist_dir
        self.backend = backend.rstrip("/")
        self.http_backend = f"http://{self.backend}"
        self.ws_backend = f"ws://{self.backend}"
        self._session: ClientSession | None = None

    async def startup(self, app: web.Application) -> None:
        from aiohttp import ClientTimeout

        self._session = ClientSession(timeout=ClientTimeout(total=None, connect=10))

    async def cleanup(self, app: web.Application) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    # ---------------- WebSocket 代理 ----------------

    async def ws_proxy(self, request: web.Request) -> web.WebSocketResponse:
        session = self._session
        if session is None:
            raise web.HTTPInternalServerError(text="http session not initialized")
        downstream = web.WebSocketResponse(
            max_msg_size=64 * 1024 * 1024,
            heartbeat=30,
        )
        await downstream.prepare(request)

        query = request.rel_url.query
        target = f"{self.ws_backend}/ws"
        if query:
            from urllib.parse import urlencode

            target = f"{target}?{urlencode(query)}"

        connection_id = uuid.uuid4().hex[:8]
        logger.info("[ws-proxy %s] 建立连接 -> %s", connection_id, target)

        try:
            async with session.ws_connect(
                target,
                max_msg_size=64 * 1024 * 1024,
                heartbeat=30,
            ) as upstream:

                async def client_to_backend() -> None:
                    async for msg in downstream:
                        if msg.type == WSMsgType.TEXT:
                            await upstream.send_str(msg.data)
                        elif msg.type == WSMsgType.BINARY:
                            await upstream.send_bytes(msg.data)
                        elif msg.type == WSMsgType.PING:
                            await upstream.ping()
                        elif msg.type == WSMsgType.PONG:
                            await upstream.pong()
                        elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                            break

                async def backend_to_client() -> None:
                    async for msg in upstream:
                        if msg.type == WSMsgType.TEXT:
                            await downstream.send_str(msg.data)
                        elif msg.type == WSMsgType.BINARY:
                            await downstream.send_bytes(msg.data)
                        elif msg.type == WSMsgType.PING:
                            await downstream.ping()
                        elif msg.type == WSMsgType.PONG:
                            await downstream.pong()
                        elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                            break

                done, pending = await asyncio.wait(
                    {
                        asyncio.create_task(client_to_backend()),
                        asyncio.create_task(backend_to_client()),
                    },
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                for task in done:
                    exc = task.exception()
                    if exc:
                        raise exc
        except ConnectionError as exc:
            logger.warning("[ws-proxy %s] 后端不可达: %s", connection_id, exc)
            if not downstream.closed:
                await downstream.close(code=1011, message=b"backend unreachable")
        # Python 3.8+ 中 asyncio.CancelledError 继承自 BaseException，
        # 不会被下方 except Exception 捕获，无需在此显式重新抛出。
        except Exception:  # noqa: BLE001
            logger.exception("[ws-proxy %s] 代理异常", connection_id)
            if not downstream.closed:
                await downstream.close(code=1011)
        finally:
            logger.info("[ws-proxy %s] 连接关闭", connection_id)
        return downstream

    # ---------------- /file-api HTTP 代理 ----------------

    async def file_api_proxy(self, request: web.Request) -> web.StreamResponse:
        session = self._session
        if session is None:
            raise web.HTTPInternalServerError(text="http session not initialized")
        tail = request.match_info.get("tail", "")
        target = f"{self.http_backend}/file-api/{tail}"
        if request.rel_url.query_string:
            target = f"{target}?{request.rel_url.query_string}"

        headers = {}
        for key, value in request.headers.items():
            if key.lower() not in _PROXY_EXCLUDED_REQUEST_HEADERS:
                headers[key] = value
        try:
            body = await request.read() if request.can_read_body else None
            async with session.request(
                request.method,
                target,
                headers=headers,
                data=body,
            ) as resp:
                payload = await resp.read()
                response_headers = {}
                for key, value in resp.headers.items():
                    if key.lower() not in _PROXY_EXCLUDED_RESPONSE_HEADERS:
                        response_headers[key] = value
                return web.Response(
                    status=resp.status,
                    body=payload,
                    headers=response_headers,
                )
        except ConnectionError as exc:
            logger.warning("[file-api] 后端不可达: %s", exc)
            return web.Response(status=502, text="backend unreachable")
        except Exception:  # noqa: BLE001
            logger.exception("[file-api] 代理异常")
            return web.Response(status=500, text="proxy error")

    # ---------------- 静态文件 ----------------

    async def static_handler(self, request: web.Request) -> web.StreamResponse:
        tail = request.match_info.get("tail", "")
        candidate = (self.dist_dir / tail).resolve()
        dist_root = self.dist_dir.resolve()
        # 防目录穿越
        if not str(candidate).startswith(str(dist_root)):
            raise web.HTTPForbidden()
        if candidate.is_file():
            return web.FileResponse(candidate)
        # SPA 回退
        index = dist_root / "index.html"
        if index.exists():
            return web.FileResponse(index)
        return web.Response(status=404, text="frontend dist not found")


def create_app(dist_dir: Path, backend: str) -> web.Application:
    interface = WebInterface(dist_dir, backend)
    app = web.Application()
    app["interface"] = interface
    app.on_startup.append(interface.startup)
    app.on_cleanup.append(interface.cleanup)
    app.router.add_get("/ws", interface.ws_proxy)
    app.router.add_route("*", "/file-api/{tail:.*}", interface.file_api_proxy)
    app.router.add_route("*", "/{tail:.*}", interface.static_handler)
    return app


def get_free_port(preferred: int = 0) -> int:
    import socket

    if preferred:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", preferred))
                return preferred
            except OSError:
                pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentOS Client 前端服务器")
    parser.add_argument("--port", type=int, default=0, help="监听端口（默认随机）")
    parser.add_argument("--backend", default=_DEFAULT_BACKEND, help="后端地址 host:port")
    parser.add_argument("--dist", default="", help="前端 dist 目录")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )

    dist_dir = Path(args.dist).resolve() if args.dist else _default_dist_dir()
    if not dist_dir.exists():
        logger.error("前端 dist 目录不存在: %s", dist_dir)
        sys.exit(2)

    port = args.port or get_free_port(17322)
    app = create_app(dist_dir, args.backend)
    logger.info("启动前端服务器: http://127.0.0.1:%s (后端: %s)", port, args.backend)
    web.run_app(app, host="127.0.0.1", port=port, print=None)


if __name__ == "__main__":
    main()
