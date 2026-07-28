"""AgentOS TUI Launcher 包入口。

整个包由若干职责单一的模块组成，对应设计文档第 7 节描述的顶层启动器模块职责。
公共数据类型（UserContext / AuthSession 等）从本包根直接导出，
方便其它模块和测试代码统一 `from agentos_tui_launcher import UserContext`。
"""

# 引入 __all__ 仅用于显式声明公共面；具体类型在子模块中实现。
from .user_context import (
    AuthSession,
    UserProfile,
    UserContext,
)
from .protocol import (
    HandoffAction,
    LaunchMode,
    TuiTarget,
)

__version__ = "0.1.0"

__all__ = [
    "AuthSession",
    "HandoffAction",
    "LaunchMode",
    "TuiTarget",
    "UserContext",
    "UserProfile",
    "__version__",
]
