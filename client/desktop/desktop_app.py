# Copyright (c) Huawei Technologies Co., Ltd. 2025-2026. All rights reserved.

"""AgentOS Client —— 独立桌面壳（pywebview）.

启动流程：
1. 后台线程启动 app_web 前端服务器（静态 + /ws、/file-api 代理到本机后端）
2. 创建 pywebview 窗口加载 http://127.0.0.1:<port>/
3. 向前端暴露 DesktopBridge（目录选择 / 文件保存 / 打开路径）

仅依赖 aiohttp + pywebview，不依赖 jiuwenswarm 包，可独立 PyInstaller 打包。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import webview  # pywebview
from aiohttp import web

# 允许直接运行（python client/desktop/desktop_app.py）时找到 app_web
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "web"))

from app_web import create_app, get_free_port, _default_dist_dir  # noqa: E402

logger = logging.getLogger("agentos-client.desktop")

_WINDOW_TITLE = "华为智能体一体机"


def _start_web_server(app: web.Application, port: int, ready: threading.Event) -> None:
    """在独立线程中运行 aiohttp 服务器。"""

    async def runner() -> None:
        runner_ = web.AppRunner(app)
        await runner_.setup()
        site = web.TCPSite(runner_, "127.0.0.1", port)
        await site.start()
        ready.set()
        # 永久运行，直到进程退出
        while True:
            await asyncio.sleep(3600)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(runner())
    except Exception:  # noqa: BLE001
        logger.exception("前端服务器线程异常退出")
    finally:
        loop.close()


class DesktopBridge:
    """暴露给前端的桌面能力（window.pywebview.api.*）。"""

    def __init__(self) -> None:
        self._window: webview.Window | None = None

    def set_window(self, window: webview.Window) -> None:
        self._window = window

    # ---------- 项目目录选择 ----------

    def select_project_directory(self) -> str | None:
        """打开系统目录选择对话框，返回所选目录绝对路径；取消返回 None。"""
        if self._window is None:
            return None
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if isinstance(result, (list, tuple)) and result:
            return str(result[0])
        return None

    # ---------- 文件下载 / 保存 ----------

    def download_file(self, url: str, filename: str) -> bool:
        """下载 URL 到用户"下载"目录（文件名冲突自动加序号）。"""
        try:
            target = self._unique_target(Path.home() / "Downloads" / (filename or "download"))
            with urllib.request.urlopen(url, timeout=60) as resp, open(target, "wb") as out:
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    out.write(chunk)
            return True
        except Exception:  # noqa: BLE001
            logger.exception("download_file 失败: %s", url)
            return False

    def save_data_url(self, data_url: str, filename: str) -> dict:
        """把 dataURL 保存到用户选择的本地路径。"""
        try:
            if not isinstance(data_url, str) or "," not in data_url:
                return {"ok": False}
            _, _, payload = data_url.partition(",")
            data = base64.b64decode(payload)
            if self._window is None:
                return {"ok": False}
            result = self._window.create_file_dialog(
                webview.SAVE_DIALOG,
                save_filename=filename or "download",
            )
            if not result:
                return {"ok": False, "cancelled": True}
            target = result if isinstance(result, str) else str(result[0])
            with open(target, "wb") as out:
                out.write(data)
            return {"ok": True}
        except Exception:  # noqa: BLE001
            logger.exception("save_data_url 失败")
            return {"ok": False}

    # ---------- 打开本地路径 ----------

    def open_path(self, path: str) -> bool:
        """用系统默认方式打开本地文件/目录。"""
        try:
            if not path:
                return False
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            return True
        except Exception:  # noqa: BLE001
            logger.exception("open_path 失败: %s", path)
            return False

    @staticmethod
    def _unique_target(path: Path) -> Path:
        if not path.exists():
            return path
        stem, suffix = path.stem, path.suffix
        for index in range(1, 1000):
            candidate = path.with_name(f"{stem} ({index}){suffix}")
            if not candidate.exists():
                return candidate
        return path


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentOS Client 桌面壳")
    parser.add_argument("--port", type=int, default=0, help="前端服务器端口（默认随机）")
    parser.add_argument("--backend", default="127.0.0.1:19000", help="后端地址 host:port")
    parser.add_argument("--dist", default="", help="前端 dist 目录")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
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

    ready = threading.Event()
    server_thread = threading.Thread(
        target=_start_web_server,
        args=(app, port, ready),
        daemon=True,
        name="agentos-web-server",
    )
    server_thread.start()
    if not ready.wait(timeout=10):
        logger.error("前端服务器启动超时")
        sys.exit(3)

    url = f"http://127.0.0.1:{port}/"
    logger.info("加载窗口: %s (后端: %s)", url, args.backend)

    bridge = DesktopBridge()
    window = webview.create_window(
        _WINDOW_TITLE,
        url,
        width=args.width,
        height=args.height,
        min_size=(1024, 640),
        js_api=bridge,
    )
    bridge.set_window(window)
    webview.start(debug=args.verbose)


if __name__ == "__main__":
    main()
