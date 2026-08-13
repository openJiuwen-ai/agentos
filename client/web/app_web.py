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
import json
import logging
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web

logger = logging.getLogger("agentos-client.web")

_DEFAULT_BACKEND = "127.0.0.1:19000"

# 远端服务器固定端口（见第二阶段设计文档）：jiuwen 后端 19000，管理面 8090
_BACKEND_PORT = 19000
_MANAGER_PORT = 8090

# 本地客户端配置（保存用户输入的服务器地址）
_CONFIG_FILE = Path.home() / ".agentos_client" / "config.json"


def _load_local_config() -> dict:
    try:
        return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_local_config(config: dict) -> None:
    try:
        _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_FILE.write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:  # noqa: BLE001
        logger.exception("保存本地配置失败: %s", _CONFIG_FILE)


def parse_server_address(raw: str) -> str:
    """解析用户输入的服务器地址，返回主机部分（IP/域名/localhost）。

    支持形式：``192.168.1.10`` / ``example.com`` / ``localhost`` /
    ``http://host`` / ``https://host:8443/path``。端口固定为 19000/8090，
    用户即便输入了端口也仅取主机部分。
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("服务器地址不能为空")
    if "://" not in text:
        text = f"http://{text}"
    host = urlparse(text).hostname
    if not host:
        raise ValueError(f"无法解析服务器地址: {raw}")
    return host

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
        self._session: ClientSession | None = None
        try:
            host = parse_server_address(backend)
        except ValueError:
            host = "127.0.0.1"
        self.set_server_host(host)

    def set_server_host(self, host: str) -> None:
        """切换远端服务器（运行时生效，/ws、/file-api、/iam-api 代理目标同步更新）。"""
        self.server_host = host
        self.backend = f"{host}:{_BACKEND_PORT}"
        self.http_backend = f"http://{self.backend}"
        self.ws_backend = f"ws://{self.backend}"
        self.mgmt_base = f"http://{host}:{_MANAGER_PORT}"

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

        # 方案A：浏览器 WebSocket 无法自定义 header，前端把 IAM 身份放进 /ws query，
        # 本代理提取后注入 X-User-Id / Authorization: Bearer header 转发给 gateway，
        # 并从转发 URL 中剔除，避免 token 出现在后端日志/URL 中。
        query = dict(request.rel_url.query)
        user_id = query.pop("user_id", None)
        access_token = query.pop("access_token", None)
        headers: dict[str, str] = {}
        if user_id:
            headers["X-User-Id"] = str(user_id)
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        target = f"{self.ws_backend}/ws"
        if query:
            from urllib.parse import urlencode

            target = f"{target}?{urlencode(query)}"

        connection_id = uuid.uuid4().hex[:8]
        logger.info("[ws-proxy %s] 建立连接 -> %s", connection_id, target)

        try:
            async with session.ws_connect(
                target,
                headers=headers,
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

    # ---------------- 本地配置 / 连接测试（/local-api） ----------------

    async def get_server_config(self, request: web.Request) -> web.Response:
        config = _load_local_config()
        return web.json_response(
            {
                "address": config.get("server_address") or None,
                "host": config.get("server_host") or None,
            }
        )

    async def test_server(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        address = body.get("address") if isinstance(body, dict) else None
        try:
            host = parse_server_address(str(address or ""))
        except ValueError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

        manager, backend = await asyncio.gather(
            self._test_manager(host), self._test_backend(host)
        )
        return web.json_response(
            {
                "ok": bool(manager["ok"] and backend["ok"]),
                "host": host,
                "manager": manager,
                "backend": backend,
            }
        )

    async def save_server(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        address = body.get("address") if isinstance(body, dict) else None
        try:
            host = parse_server_address(str(address or ""))
        except ValueError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

        self.set_server_host(host)
        _save_local_config(
            {"server_address": str(address).strip(), "server_host": host}
        )
        logger.info("远端服务器已切换并保存: %s", host)
        return web.json_response({"ok": True, "host": host})

    async def _test_manager(self, host: str) -> dict:
        """管理面健康检查：GET http://host:8090/health。"""
        session = self._session
        if session is None:
            return {"ok": False, "error": "本地服务尚未就绪"}
        url = f"http://{host}:{_MANAGER_PORT}/health"
        try:
            async with session.get(url, timeout=ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    return {"ok": True}
                return {"ok": False, "error": f"管理面健康检查返回 HTTP {resp.status}"}
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": f"管理面连接失败（{host}:{_MANAGER_PORT}）：{exc}",
            }

    async def _test_backend(self, host: str) -> dict:
        """jiuwen 后端探测：TCP 连接 host:19000。"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, _BACKEND_PORT), timeout=5
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
            return {"ok": True}
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": f"jiuwen 后端连接失败（{host}:{_BACKEND_PORT}）：{exc}",
            }

    # ---------------- 管理面 IAM 代理（/iam-api/* -> http://host:8090/api/v1/*） ----------------

    async def iam_api_proxy(self, request: web.Request) -> web.StreamResponse:
        session = self._session
        if session is None:
            raise web.HTTPInternalServerError(text="http session not initialized")
        tail = request.match_info.get("tail", "")
        target = f"{self.mgmt_base}/api/v1/{tail}"
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
            logger.warning("[iam-api] 管理面不可达: %s", exc)
            return web.Response(status=502, text="manager unreachable")
        except Exception:  # noqa: BLE001
            logger.exception("[iam-api] 代理异常")
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
    # 启动时若本地 config 已保存服务器地址，直接应用（无需再弹窗）
    saved_host = _load_local_config().get("server_host")
    if saved_host:
        try:
            interface.set_server_host(parse_server_address(str(saved_host)))
            logger.info("已从本地配置加载远端服务器: %s", saved_host)
        except ValueError:
            logger.warning("本地配置中的服务器地址无效，忽略: %s", saved_host)
    app = web.Application()
    app["interface"] = interface
    app.on_startup.append(interface.startup)
    app.on_cleanup.append(interface.cleanup)
    app.router.add_get("/ws", interface.ws_proxy)
    app.router.add_route("*", "/file-api/{tail:.*}", interface.file_api_proxy)
    app.router.add_get("/local-api/server", interface.get_server_config)
    app.router.add_post("/local-api/server/test", interface.test_server)
    app.router.add_post("/local-api/server", interface.save_server)
    app.router.add_route("*", "/iam-api/{tail:.*}", interface.iam_api_proxy)
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
