"""非敏感客户端配置。

只存储 ClientConfig 中的非敏感字段：服务地址、最近登录用户元数据等。
密码 / refresh token / access token 严禁写入此处；
那些由 credential_store.py 通过 OS 安全存储管理。

公共契约第 4.1 节定义本模块的行为：
- 使用操作系统约定的用户配置目录，不写入仓库或当前工作目录。
- 对缺失文件返回默认配置；对损坏文件返回 ConfigError，不静默采用部分配置。
- 原子写入配置，避免进程中断留下半个文件。
"""

from __future__ import annotations

import json
import os
import os.path
import tempfile
from dataclasses import asdict, dataclass
from typing import Protocol


# ============================================================================
# 配置数据类型
# ============================================================================


@dataclass(frozen=True)
class ClientConfig:
    """非敏感客户端配置。

    `last_user_id` 与 `last_username` 仅用于：
      - 定位安全存储中的 refresh token；
      - 在登录提示中显示最近用户。
    绝不可作为已通过认证的证明。
    """

    api_url: str | None
    websocket_url: str | None
    last_user_id: str | None
    last_username: str | None
    allow_insecure_http: bool = False
    # gateway WS 地址，用于 3rdagent.switch 调用；缺失时从 websocket_url 推导。
    gateway_url: str | None = None


# ============================================================================
# ConfigStore
# ============================================================================


class ConfigStore(Protocol):
    """配置存储协议。"""

    def load(self) -> ClientConfig:
        ...

    def save(self, config: ClientConfig) -> None:
        ...


class FileConfigStore:
    """基于 JSON 文件的 ConfigStore 实现。

    配置文件位于操作系统用户配置目录下，避免污染仓库或当前工作目录。
    原子写入：先写到临时文件，再原子重命名到目标路径。
    """

    # 配置文件名，固定；不暴露给上层以便未来调整布局。
    CONFIG_FILENAME = "config.json"
    CONFIG_DIR_ENV = "AGENTOS_TUI_CONFIG_DIR"

    def __init__(self, config_dir: str | None = None) -> None:
        # 允许通过参数或环境变量指定配置目录，便于测试。
        # 否则使用操作系统默认路径。
        self._config_dir = config_dir or default_config_dir()

    # ------------------------------------------------------------------
    # Protocol 实现
    # ------------------------------------------------------------------

    def load(self) -> ClientConfig:
        path = self.config_path()
        if not os.path.exists(path):
            # 缺失文件返回默认配置。
            return ClientConfig(
                api_url=None,
                websocket_url=None,
                last_user_id=None,
                last_username=None,
                allow_insecure_http=False,
                gateway_url=None,
            )

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            # 损坏文件返回可识别的 ConfigError，不静默采用部分配置。
            from . import errors

            raise errors.ConfigError(f"Config file corrupted: {path}") from exc

        # 校验字段类型，缺失字段使用默认值。
        # 不允许未知字段触发错误（前向兼容），但缺失必需类型必须报错。
        try:
            return ClientConfig(
                api_url=data.get("api_url"),
                websocket_url=data.get("websocket_url"),
                last_user_id=data.get("last_user_id"),
                last_username=data.get("last_username"),
                allow_insecure_http=bool(data.get("allow_insecure_http", False)),
                gateway_url=data.get("gateway_url"),
            )
        except (TypeError, ValueError) as exc:
            from . import errors

            raise errors.ConfigError(f"Config file schema invalid: {path}") from exc

    def save(self, config: ClientConfig) -> None:
        path = self.config_path()
        # 确保目录存在。
        os.makedirs(self._config_dir, exist_ok=True)

        # 原子写入：写到临时文件后重命名。
        # Windows 上 os.replace 可以原子覆盖目标文件。
        data = asdict(config)
        # 过滤 None 以减小文件体积；load() 会用默认值补回。
        data = {k: v for k, v in data.items() if v is not None}

        # tempfile 同目录，保证同文件系统跨设备不会被 rename 拒绝。
        fd, tmp_path = tempfile.mkstemp(
            prefix=".config-", suffix=".tmp", dir=self._config_dir
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        except Exception:
            # 清理临时文件，避免遗留垃圾文件。
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def config_path(self) -> str:
        return os.path.join(self._config_dir, self.CONFIG_FILENAME)


def sys_platform() -> str:
    """包一层 sys.platform，便于测试 mock。"""
    import sys

    return sys.platform


def default_config_dir() -> str:
    """返回操作系统约定的配置目录。

    Windows: %APPDATA%\\AgentOS\\tui-launcher
    macOS:   ~/Library/Application Support/AgentOS/tui-launcher
    Linux:   $XDG_CONFIG_HOME/agentos/tui-launcher or ~/.config/agentos/tui-launcher

    供 FileConfigStore 和 FileCredentialStore 共用，保证配置与凭据同目录。
    """
    env_dir = os.environ.get(FileConfigStore.CONFIG_DIR_ENV)
    if env_dir:
        return env_dir

    if os.name == "nt":  # Windows
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "AgentOS", "tui-launcher")
    if sys_platform() == "darwin":  # macOS
        home = os.path.expanduser("~")
        return os.path.join(home, "Library", "Application Support", "AgentOS", "tui-launcher")
    # Linux / 其他 POSIX
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )
    return os.path.join(xdg, "agentos", "tui-launcher")
