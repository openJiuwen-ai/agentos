"""父子进程监督协议：动作码、环境变量与枚举。

本模块是 AgentOS launcher 与 JiuwenSwarm TUI 之间的"能力声明"所有者。
JiuwenSwarm TUI 必须从环境变量读取这些值，不得在子项目侧硬编码 88 / 89，
否则 launcher 与 TUI 之间会出现版本不一致。

新设计（tui-switch-cc-design-new.md）中，SWITCH_CC 不再启动本地 cc-tui 子进程，
而是由 launcher 读取子进程 stdout 的 handoff JSON，通过 gateway WS 获取 SSH 端点，
再通过 SSH 隧道连接远程三方 Agentos。因此移除了 RETURN_EXIT_CODE / cc-tui 本地执行
相关协议变量。

公共契约第 6 节、第 9.1 节定义本模块的全部行为。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


# ============================================================================
# 枚举类型
# ============================================================================


class LaunchMode(str, Enum):
    """启动模式。

    - MANAGED：托管登录模式，由 launcher 注入 `--user-id` 与 `--token`，
      并在运行中收到 REAUTH_REQUIRED 时自动刷新身份。
    - EXPLICIT：显式兼容模式，用户/脚本已经提供 `--user-id` 与可选 `--token`，
      launcher 不持有 refresh token，不进行自动重新认证。
    """

    MANAGED = "managed"
    EXPLICIT = "explicit"


class TuiTarget(str, Enum):
    """受支持的前台 TUI 目标，使用白名单，禁止接受任意程序名。

    注意：新设计下 CC 不再作为本地子进程启动；三方 Agentos 通过 gateway SSH
    隧道访问。这里保留枚举值用于 resolver 兼容与未来扩展。
    """

    PRIMARY = "jiuwenswarm-tui"
    CC = "cc-tui"


class HandoffAction(str, Enum):
    """子进程通过动作退出码向 launcher 请求的"交接动作"。

    注意：
    - `SWITCH_CC` 表示请求切换到三方 Agentos；launcher 读取 stdout handoff JSON
      后通过 gateway WS + SSH 隧道完成切换，不再启动本地 cc-tui 子进程。
    - `REAUTH_REQUIRED` 表示把控制权交还 launcher 进行身份刷新，
      并不切换到另一个 TUI 目标。
    """

    SWITCH_CC = "switch-cc"
    REAUTH_REQUIRED = "reauth-required"


# ============================================================================
# 协议常量（环境变量名 + 固定动作码）
# ============================================================================


# 1 表示当前 TUI 由 AgentOS launcher 托管；其它值或缺失均视为"非托管"。
ENV_SUPERVISED = "AGENTOS_TUI_SUPERVISED"
ENV_SUPERVISED_VALUE = "1"

# 请求切换到三方 Agentos 的固定动作码（十进制，1..255 可移植范围）。
ENV_SWITCH_CC_EXIT_CODE = "AGENTOS_TUI_SWITCH_CC_EXIT_CODE"
SWITCH_CC_EXIT_CODE = 88

# 请求 launcher 刷新身份并重启主 TUI 的动作码；
# 仅在托管登录模式才会注入，显式模式不注入。
ENV_REAUTH_EXIT_CODE = "AGENTOS_TUI_REAUTH_EXIT_CODE"
REAUTH_EXIT_CODE = 89

# cc-tui 可执行文件路径（可选）。
# 接口文档第 2 节：TUI 端 checkHandoff() 可能读取此变量做目标可用性预检。
# 新设计下 cc-tui 不再本地执行，launcher 不强制注入；
# 若 base_env 已包含此变量则透传，用户也可通过环境变量预设。
ENV_CC_TUI_EXECUTABLE = "AGENTOS_CC_TUI_EXECUTABLE"


# 一个不可变快照，对应每次启动主 TUI 时的协议状态。
# 每次启动主 TUI 必须形成新的快照；退出分类时只使用本次快照，
# 不允许在退出分类时重新读取环境/外部配置。
@dataclass(frozen=True)
class ProtocolSnapshot:
    """单次启动主 TUI 时的协议快照。

    `classify_exit()` 必须基于该快照判断，不允许在退出时再次读取环境。
    """

    supervised: bool
    switch_cc_exit_code: int
    reauth_exit_code: int | None  # 显式模式为 None


# 用于注入到子进程环境变量的字典键集合，方便 supervisor 在需要时移除。
_ALL_PROTOCOL_ENV_KEYS: tuple[str, ...] = (
    ENV_SUPERVISED,
    ENV_SWITCH_CC_EXIT_CODE,
    ENV_REAUTH_EXIT_CODE,
)


def strip_protocol_env(base_env: Mapping[str, str]) -> dict[str, str]:
    """从基础环境中剥离 JiuwenSwarm 专用监督变量。

    用于清理可能残留的协议变量，避免外部注入伪造能力。
    """
    return {k: v for k, v in base_env.items() if k not in _ALL_PROTOCOL_ENV_KEYS}
