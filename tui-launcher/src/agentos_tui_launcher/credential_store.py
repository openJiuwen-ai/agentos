"""refresh token 的安全存储抽象。

公共契约第 4.2 节定义本模块行为：
- 使用 Windows Credential Manager / macOS Keychain / Linux Secret Service
  或等价安全存储。
- 以规范化服务 origin 和 user_id 隔离凭据。
- delete_refresh_token() 幂等；凭据不存在时也视为成功。
- 安全存储不可用与凭据不存在区分：
    * 不可用 -> CredentialStoreUnavailable
    * 损坏   -> CredentialCorrupted
    * 不存在 -> 返回 None
- 安全存储不可用时只允许本次会话登录，不得降级为明文文件。

实现说明：
- 实际项目使用 `keyring` 第三方库，跨平台访问 OS 安全存储。
- 为了便于在无 keyring 的环境运行与单元测试，本模块提供：
    * KeyringCredentialStore：依赖 keyring 的生产实现。
    * MemoryCredentialStore：仅用于测试或本次会话回退。
    * FileCredentialStore：keyring 不可用时的跨进程持久化回退，
      文件权限 0600（POSIX）保护，安全性低于 OS keyring。
- 用户在开发时，如果系统未安装 OS 凭据服务，KeyringCredentialStore 会抛
  CredentialStoreUnavailable，由上层选择本次会话登录或显式选择其他后端。
"""

from __future__ import annotations

import json
import os
import os.path
import tempfile
from dataclasses import dataclass
from typing import Optional, Protocol

from . import errors


# ============================================================================
# 公共数据类型
# ============================================================================


@dataclass(frozen=True)
class CredentialKey:
    """凭据键。

    `service_origin` 必须是规范化后的 API origin，
    不得包含查询串、片段、用户名或密码。
    `user_id` 必须是服务端签发的非空稳定标识。
    """

    service_origin: str
    user_id: str

    def backend_key(self) -> str:
        """组合为安全存储后端的键名，避免不同环境或用户之间串用 token。"""
        return f"agentos-tui:{self.service_origin}:{self.user_id}"


# ============================================================================
# CredentialStore 协议
# ============================================================================


class CredentialStore(Protocol):
    """凭据存储协议。"""

    def get_refresh_token(self, key: CredentialKey) -> Optional[str]:
        ...

    def set_refresh_token(self, key: CredentialKey, token: str) -> None:
        ...

    def delete_refresh_token(self, key: CredentialKey) -> None:
        ...


# ============================================================================
# Keyring 实现
# ============================================================================


# keyring 服务名，固定值，避免不同应用混用同一 keyring 命名空间。
_KEYRING_SERVICE_NAME = "AgentOS-TUI-Launcher"


class KeyringCredentialStore:
    """基于 `keyring` 库的 CredentialStore 实现。

    生产环境使用；如果系统未安装 OS 凭据服务，初始化阶段或调用阶段
    会抛 CredentialStoreUnavailable，由上层选择本次会话登录。
    """

    # 探测后端时使用的占位 key（不会真的写入，仅用于 get 探活）。
    _PROBE_USER = "__agentos_tui_probe__"

    def __init__(self) -> None:
        # 延迟导入 keyring，避免在不需要时强制依赖。
        try:
            import keyring  # type: ignore
            import keyring.errors  # type: ignore
        except ImportError as exc:  # pragma: no cover - 测试环境应预装 keyring
            raise errors.CredentialStoreUnavailable(
                "keyring library not installed; cannot access OS secure storage."
            ) from exc

        self._keyring = keyring
        self._keyring_errors = keyring.errors

        # 探测后端是否真的可用：对一个不存在的 key 调用 get_password。
        # 如果后端不可用（如 Linux 上 D-Bus 未启动 / gnome-keyring 未运行），
        # 这里会抛 KeyringError，提前在 init 阶段就触发回退，
        # 避免登录成功后写入时才发现后端不可用。
        try:
            self._keyring.get_password(
                _KEYRING_SERVICE_NAME, self._PROBE_USER
            )
        except self._keyring_errors.KeyringError as exc:
            raise errors.CredentialStoreUnavailable(
                "OS secure storage unavailable."
            ) from exc
        except Exception as exc:
            # 其他异常（如 D-Bus ImportError 透传）也按不可用处理。
            raise errors.CredentialStoreUnavailable(
                "OS secure storage unavailable."
            ) from exc

    def get_refresh_token(self, key: CredentialKey) -> Optional[str]:
        try:
            value = self._keyring.get_password(
                _KEYRING_SERVICE_NAME, key.backend_key()
            )
        except self._keyring_errors.KeyringError as exc:
            # keyring 后端不可用（如 D-Bus 未启动、Keychain 锁定）。
            raise errors.CredentialStoreUnavailable(
                "OS secure storage unavailable."
            ) from exc
        except Exception as exc:  # pragma: no cover - 防御性处理
            raise errors.CredentialCorrupted(
                "Credential stored value cannot be decoded."
            ) from exc

        if value is None:
            return None
        return value

    def set_refresh_token(self, key: CredentialKey, token: str) -> None:
        try:
            self._keyring.set_password(
                _KEYRING_SERVICE_NAME, key.backend_key(), token
            )
        except self._keyring_errors.KeyringError as exc:
            raise errors.CredentialStoreUnavailable(
                "OS secure storage unavailable."
            ) from exc

    def delete_refresh_token(self, key: CredentialKey) -> None:
        # delete_refresh_token 必须幂等。
        try:
            self._keyring.delete_password(_KEYRING_SERVICE_NAME, key.backend_key())
        except self._keyring_errors.PasswordDeleteError:
            # 凭据不存在：视为成功。
            return
        except self._keyring_errors.KeyringError as exc:
            raise errors.CredentialStoreUnavailable(
                "OS secure storage unavailable."
            ) from exc


# ============================================================================
# 内存实现（仅供测试 / 一次性会话回退）
# ============================================================================


class MemoryCredentialStore:
    """进程内字典实现，仅用于测试或本次会话内存 AuthSession。

    **绝不**用于持久化真实 refresh token；
    进程结束即丢失。
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get_refresh_token(self, key: CredentialKey) -> Optional[str]:
        return self._store.get(key.backend_key())

    def set_refresh_token(self, key: CredentialKey, token: str) -> None:
        self._store[key.backend_key()] = token

    def delete_refresh_token(self, key: CredentialKey) -> None:
        # 幂等：不存在也视为成功。
        self._store.pop(key.backend_key(), None)


# ============================================================================
# 文件实现（keyring 不可用时的跨进程回退）
# ============================================================================


class FileCredentialStore:
    """基于文件（带权限保护）的 CredentialStore 实现。

    作为 keyring 不可用时的回退方案，用于支持 CLI 多命令场景下的跨进程
    凭据共享（例如 `agentos-tui login` 后 `agentos-tui whoami` 能读到 token）。

    安全性说明：
    - POSIX 平台文件权限 0600（仅所有者可读写）。
    - Windows 平台依赖父目录 ACL（用户配置目录默认仅当前用户可访问）。
    - 安全性低于 OS keyring（keyring 有独立会话加密 / 系统级隔离），
      但能跨进程持久化，适用于无 keyring 的 Linux SSH 等环境。

    存储格式：JSON 字典 {backend_key: refresh_token}。
    原子写入：先写临时文件后 os.replace，避免进程中断留下半个文件。
    """

    CREDENTIALS_FILENAME = "credentials.json"

    def __init__(self, config_dir: str | None = None) -> None:
        # 延迟导入，避免与 config.py 形成导入环。
        from .config import default_config_dir

        self._config_dir = config_dir or default_config_dir()
        self._store: dict[str, str] = {}
        self._load()

    # ------------------------------------------------------------------
    # Protocol 实现
    # ------------------------------------------------------------------

    def get_refresh_token(self, key: CredentialKey) -> Optional[str]:
        return self._store.get(key.backend_key())

    def set_refresh_token(self, key: CredentialKey, token: str) -> None:
        self._store[key.backend_key()] = token
        self._save()

    def delete_refresh_token(self, key: CredentialKey) -> None:
        # 幂等：不存在也视为成功。
        if key.backend_key() in self._store:
            del self._store[key.backend_key()]
            self._save()

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _credentials_path(self) -> str:
        return os.path.join(self._config_dir, self.CREDENTIALS_FILENAME)

    def _load(self) -> None:
        """从文件加载凭据。文件不存在或损坏时回退到空字典。"""
        path = self._credentials_path()
        if not os.path.exists(path):
            self._store = {}
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            # 损坏的凭据文件视为不可用，避免静默丢失已有凭据。
            raise errors.CredentialCorrupted(
                f"Credentials file corrupted: {path}"
            ) from exc

        if isinstance(data, dict):
            # 只接受 str -> str 的映射，避免恶意结构。
            self._store = {
                str(k): str(v) for k, v in data.items() if isinstance(v, str)
            }
        else:
            self._store = {}

    def _save(self) -> None:
        """原子写入凭据文件，并设置权限 0600（POSIX）。"""
        path = self._credentials_path()
        os.makedirs(self._config_dir, exist_ok=True)

        # 原子写入：先写临时文件后 os.replace。
        # 临时文件与目标同目录，保证同文件系统跨设备不会被 rename 拒绝。
        fd, tmp_path = tempfile.mkstemp(
            prefix=".credentials-", suffix=".tmp", dir=self._config_dir
        )
        try:
            # POSIX 下临时文件默认权限可能是 0600 以外值，显式收紧。
            if os.name != "nt":
                os.fchmod(fd, 0o600)

            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._store, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)

            # 再次显式设置权限 0600（覆盖可能继承的 umask）。
            if os.name != "nt":
                os.chmod(path, 0o600)
        except Exception:
            # 清理临时文件，避免遗留垃圾文件。
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
