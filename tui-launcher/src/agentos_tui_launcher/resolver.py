"""白名单解析可执行文件：jiuwenswarm-tui / cc-tui。

公共契约第 4.6 节定义本模块行为：
- 只接受 TuiTarget.PRIMARY 和 TuiTarget.CC；不得接受用户给出的任意程序名。
- 依次检查环境变量和 PATH 查找可执行文件。
- 返回规范化绝对路径，并验证目标是当前平台可执行的普通文件或受支持入口。
- 启动前通过 revalidate() 再检查一次，缩小检查与使用之间的竞态窗口。
- 主 TUI 缺失是启动失败；cc-tui 缺失不得阻止主 TUI 启动，但 /switch-claude 能力必须标记为不可用。
"""

from __future__ import annotations

import os
import os.path
from dataclasses import dataclass
from typing import Optional, Protocol

from .protocol import TuiTarget


# ============================================================================
# 公共数据类型
# ============================================================================


@dataclass(frozen=True)
class ResolvedExecutable:
    """解析后的可执行文件路径。

    `absolute_path` 必须是已规范化的绝对路径，不得是 shell 片段。
    """

    target: TuiTarget
    absolute_path: str


# ============================================================================
# ExecutableResolver 协议
# ============================================================================


class ExecutableResolver(Protocol):
    """可执行文件解析协议。"""

    def resolve(self, target: TuiTarget) -> Optional[ResolvedExecutable]:
        ...

    def revalidate(self, executable: ResolvedExecutable) -> bool:
        ...


# ============================================================================
# 默认实现
# ============================================================================


class ExecutableResolverImpl:
    """默认 ExecutableResolver 实现。

    解析顺序：
      1. AGENTOS_TUI_<TARGET_UPPER>_PATH 环境变量（用于测试与显式覆盖）。
      2. PATH 上的稳定 console entry point。

    主 TUI 缺失：resolve() 返回 None，CLI 视为启动失败（退出码 5）。
    cc-tui 缺失：resolve() 返回 None，CLI 仍可启动主 TUI，但 /switch-claude 不可用。
    """

    def resolve(self, target: TuiTarget) -> Optional[ResolvedExecutable]:
        # 1. 环境变量优先（便于测试和显式覆盖）。
        env_var = f"AGENTOS_TUI_{target.name}_PATH"
        env_path = os.environ.get(env_var)
        if env_path:
            resolved = self._validate_path(target, env_path)
            if resolved is not None:
                return resolved

        # 2. PATH 上的稳定 console entry point。
        import shutil

        name = target.value
        path = shutil.which(name)
        if path:
            resolved = self._validate_path(target, path)
            if resolved is not None:
                return resolved

        return None

    def revalidate(self, executable: ResolvedExecutable) -> bool:
        """启动前再次校验，缩小检查与使用之间的竞态窗口。"""
        return self._is_executable(executable.absolute_path)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _validate_path(
        self, target: TuiTarget, path: str
    ) -> Optional[ResolvedExecutable]:
        """校验路径并返回 ResolvedExecutable。"""
        if not self._is_executable(path):
            return None
        abs_path = os.path.abspath(path)
        abs_path = os.path.normpath(abs_path)
        return ResolvedExecutable(target=target, absolute_path=abs_path)

    @staticmethod
    def _is_executable(path: str) -> bool:
        """跨平台判断路径是否为可执行文件。"""
        if not os.path.isfile(path):
            return False
        if os.name == "nt":
            return True
        return os.access(path, os.X_OK)
