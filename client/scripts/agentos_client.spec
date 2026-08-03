# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec —— AgentOS Client 桌面可执行文件.

在 agentos_client/client 目录下运行（或通过 build_windows.py 自动调用，
其以 cwd=client 启动 PyInstaller）：
    pyinstaller scripts/agentos_client.spec --noconfirm --clean
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

CLIENT = Path.cwd()  # 即 agentos_client/client
FRONTEND_DIST = CLIENT / "web" / "frontend" / "dist"

if not FRONTEND_DIST.exists():
    raise SystemExit(f"前端 dist 不存在，请先执行 npm run build: {FRONTEND_DIST}")

datas = [(str(FRONTEND_DIST), "agentos_web_dist")] + collect_data_files("webview")
hiddenimports = [
    "webview",
    "aiohttp",
    "aiohttp.web",
    "aiohttp.client",
    "multidict",
    "yarl",
    "frozenlist",
    "aiosignal",
    "clr",
    "clr_loader",
    "pythonnet",
] + collect_submodules("webview.platforms")

a = Analysis(
    [str(CLIENT / "desktop" / "desktop_app.py")],
    pathex=[str(CLIENT / "web")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "wx",
        "gi",
        "cefpython3",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AgentOSClient",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
