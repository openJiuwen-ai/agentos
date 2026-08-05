#!/usr/bin/env python3
"""AgentOS Client —— Windows 一键打包脚本.

用法（在 agentos_client/ 目录下）：
    python client/scripts/build_windows.py [--skip-frontend] [--console]

流程：
1. 构建前端（npm install + npm run build）——可用 --skip-frontend 跳过
2. 检查/安装桌面依赖（requirements-desktop.txt）
3. PyInstaller 打包为 client/dist/AgentOSClient.exe（单文件、无控制台）
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("agentos-client.build")

CLIENT = Path(__file__).resolve().parent.parent  # agentos_client/client
FRONTEND = CLIENT / "web" / "frontend"
SPEC = CLIENT / "scripts" / "agentos_client.spec"
DIST_OUT = CLIENT / "dist"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    logger.info(">>> %s%s", " ".join(cmd), f"  (cwd={cwd})" if cwd else "")
    subprocess.run(cmd, cwd=cwd, check=True)


def npm_cmd() -> str:
    return "npm.cmd" if sys.platform.startswith("win") else "npm"


def build_frontend() -> None:
    if not (FRONTEND / "node_modules").exists():
        run([npm_cmd(), "install"], cwd=FRONTEND)
    run([npm_cmd(), "run", "build"], cwd=FRONTEND)


def ensure_python_deps() -> None:
    run([
        sys.executable, "-m", "pip", "install", "-r",
        str(SPEC.parent / "requirements-desktop.txt"),
    ])


def pyinstaller_build(console: bool) -> None:
    args = [
        sys.executable, "-m", "PyInstaller",
        str(SPEC),
        "--noconfirm",
        "--clean",
        "--distpath", str(DIST_OUT),
        "--workpath", str(CLIENT / "dist" / "build"),
    ]
    run(args, cwd=CLIENT)
    if console:
        # 重新以 console 模式打包便于调试：直接提示，不重复构建
        logger.info("提示：console 调试版本请在 spec 中将 console=False 改为 True 后重新执行。")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="AgentOS Client Windows 打包")
    parser.add_argument("--skip-frontend", action="store_true", help="跳过前端构建（使用现有 dist）")
    parser.add_argument("--skip-deps", action="store_true", help="跳过 Python 依赖安装")
    parser.add_argument("--console", action="store_true", help="提示如何构建带控制台的调试版")
    args = parser.parse_args()

    if not args.skip_frontend:
        build_frontend()
    dist_dir = FRONTEND / "dist"
    if not dist_dir.exists():
        raise SystemExit(f"前端 dist 不存在: {dist_dir}")

    if not args.skip_deps:
        ensure_python_deps()

    pyinstaller_build(args.console)

    exe = DIST_OUT / "AgentOSClient.exe"
    logger.info("========================================")
    if exe.exists():
        logger.info("打包完成: %s", exe)
        logger.info("文件大小: %.1f MB", exe.stat().st_size / 1024 / 1024)
    else:
        logger.info("打包结束，请检查输出目录: %s", DIST_OUT)
    logger.info("运行前请确保 jiuwenswarm 后端已启动（默认 127.0.0.1:19000）。")
    logger.info("========================================")


if __name__ == "__main__":
    main()
