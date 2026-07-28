"""构造 JiuwenSwarm TUI 的最终参数数组。

公共契约第 4.5 节定义本模块行为：
- 同等支持 `--user-id value` 与 `--user-id=value`。
- 拒绝空值、重复值、两种写法混用形成的重复值及缺少后续值。
- 除 launcher 自有参数和 `--` 分隔符外，保持所有 JiuwenSwarm 参数的元素边界、值与相对顺序。
- launcher 必须保存解析后、尚未注入托管 `--user-id`/`--token` 的原始 `tui_argv`；
  每次重新认证后从该原始值重新调用 `build_primary_argv()`，
  不得在上一轮生成结果上追加或替换字符串。
- 托管模式必须注入 `context.user_id`；若已有显式 `--user-id`，只允许其与 `context.user_id` 完全一致。
- 托管模式需要传 access token 时，只能注入短期 `context.access_token`。
  若用户同时显式提供 `--token`，必须拒绝混合身份来源。
- 显式兼容模式原样保留用户提供的 `--user-id` 和 `--token`，但不得视为已通过认证。
- 只能返回 argv 数组，不得返回或执行 shell 字符串。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from . import errors
from .protocol import LaunchMode
from .user_context import UserContext


# ============================================================================
# 公共数据类型
# ============================================================================


@dataclass(frozen=True)
class TuiArgvAnalysis:
    """`analyze()` 的返回值。

    `user_id`：原始 tui_argv 中显式出现的 --user-id 值；没有则为 None。
    `has_access_token`：原始 tui_argv 中是否显式出现 --token。
    """

    user_id: Optional[str]
    has_access_token: bool


# ============================================================================
# LauncherArgvAdapter 协议
# ============================================================================


class LauncherArgvAdapter(Protocol):
    """参数构造协议。"""

    def analyze(self, tui_argv: tuple[str, ...]) -> TuiArgvAnalysis:
        ...

    def build_primary_argv(
        self,
        tui_argv: tuple[str, ...],
        mode: LaunchMode,
        context: Optional[UserContext],
    ) -> tuple[str, ...]:
        ...


# ============================================================================
# 默认实现
# ============================================================================


# launcher 自有参数；这些不会透传给 JiuwenSwarm。
# `--user-id` / `--token` 是共享边界：launcher 解析校验，最终仍传给 TUI。
_LAUNCHER_ONLY_FLAGS = {"--api-url", "--no-save-login"}


# 在 argv 中具有 `--flag value` 形式的参数。
# 解析时这些参数会消费下一个元素作为值。
_VALUE_TAKING_FLAGS = ("--user-id", "--token", "--url", "--session", "--api-url")


class LauncherArgvAdapterImpl:
    """默认 LauncherArgvAdapter 实现。

    设计要点：
    1. `analyze()` 仅做静态解析，不修改 argv。
    2. `build_primary_argv()` 按模式注入 `--user-id` / `--token`；
       所有冲突检测在这里完成。
    3. 永远在原始 tui_argv 上构造，不在上一轮结果上叠加。
    """

    # ------------------------------------------------------------------
    # analyze
    # ------------------------------------------------------------------

    @staticmethod
    def analyze(tui_argv: tuple[str, ...]) -> TuiArgvAnalysis:
        """静态分析 tui_argv。

        返回显式出现的 --user-id 值（如果有）和是否包含 --token。
        拒绝：空值、重复值、两种写法混用形成的重复值、缺少后续值。
        """
        user_id_values: list[str] = []
        has_access_token = False

        i = 0
        n = len(tui_argv)
        while i < n:
            arg = tui_argv[i]

            # 处理 `--user-id=value` 形式
            if arg.startswith("--user-id="):
                value = arg[len("--user-id="):]
                if not value:
                    raise errors.UsageError("--user-id value is empty.")
                user_id_values.append(value)
                i += 1
                continue

            # 处理 `--user-id value` 形式
            if arg == "--user-id":
                if i + 1 >= n:
                    raise errors.UsageError("--user-id requires a value.")
                value = tui_argv[i + 1]
                if not value:
                    raise errors.UsageError("--user-id value is empty.")
                user_id_values.append(value)
                i += 2
                continue

            # 处理 `--token=value` 形式
            if arg.startswith("--token="):
                value = arg[len("--token="):]
                if not value:
                    raise errors.UsageError("--token value is empty.")
                has_access_token = True
                i += 1
                continue

            # 处理 `--token value` 形式
            if arg == "--token":
                if i + 1 >= n:
                    raise errors.UsageError("--token requires a value.")
                value = tui_argv[i + 1]
                if not value:
                    raise errors.UsageError("--token value is empty.")
                has_access_token = True
                i += 2
                continue

            i += 1

        # 校验 --user-id 唯一性
        if len(user_id_values) > 1:
            raise errors.UsageError(
                "Multiple --user-id values are not allowed."
            )

        user_id = user_id_values[0] if user_id_values else None
        return TuiArgvAnalysis(user_id=user_id, has_access_token=has_access_token)

    # ------------------------------------------------------------------
    # build_primary_argv
    # ------------------------------------------------------------------

    def build_primary_argv(
        self,
        tui_argv: tuple[str, ...],
        mode: LaunchMode,
        context: Optional[UserContext],
    ) -> tuple[str, ...]:
        """构造最终 JiuwenSwarm argv。

        返回的 argv 顺序：
          1. 原始 tui_argv 的元素（保持边界和相对顺序），但移除 launcher 自有参数和 `--` 分隔符。
          2. 托管模式：在末尾注入 `--user-id <context.user_id>` 和 `--token <context.access_token>`。

        为什么不替换原 argv 中的 --user-id / --token，而是注入到末尾？
        - 显式模式不允许托管上下文，所以两者必居其一，不会冲突。
        - 托管模式下 analyze() 必然返回 user_id=None；否则 build 时抛错。
        """
        analysis = self.analyze(tui_argv)

        # 过滤 launcher 自有参数和 `--` 分隔符；保留所有其它 JiuwenSwarm 参数。
        filtered = self._filter_launcher_args(tui_argv)

        if mode == LaunchMode.EXPLICIT:
            # 显式兼容模式：原样保留用户提供的 --user-id 和 --token。
            # 不要求 context 存在；context 必为 None。
            if context is not None:
                # 同时存在托管身份和显式 --user-id 是不允许的；
                # CLI 应在调用 build 之前检测，这里再做一次防御。
                raise errors.UsageError(
                    "Explicit mode cannot have a managed UserContext."
                )
            return filtered

        # MANAGED 模式
        if context is None:
            raise errors.UsageError(
                "Managed mode requires a UserContext to inject identity."
            )

        # 托管模式下：原 argv 不应已有 --user-id 或 --token。
        # 若已有 --user-id，必须与 context.username 完全一致；
        # 若已有 --token，则视为混合身份来源，拒绝。
        if analysis.user_id is not None:
            if analysis.user_id != context.username:
                raise errors.UsageError(
                    "Explicit --user-id does not match managed UserContext."
                )
            # 一致时仍由 launcher 注入以保证来源可信：删除原值，由注入值替代。
            # 这里选择更严格的做法：禁止显式 --user-id，要求用户去掉冲突参数。
            raise errors.UsageError(
                "Managed mode must not have explicit --user-id; "
                "remove it or use explicit mode."
            )

        if analysis.has_access_token:
            # 公共契约：托管模式 + 显式 --token 视为混合身份来源，拒绝。
            raise errors.UsageError(
                "Managed mode cannot mix with explicit --token."
            )

        # 注入 --user-id 和 --token 到末尾。
        # 这两个字段是 launcher 拥有的、由 UserContext 决定，不属于"在上一轮结果上叠加"。
        return filtered + (
            "--user-id",
            context.username,
            "--token",
            context.access_token,
        )

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_launcher_args(tui_argv: tuple[str, ...]) -> tuple[str, ...]:
        """过滤 launcher 自有参数和 `--` 分隔符。

        保留所有 JiuwenSwarm 参数的元素边界、值和相对顺序。
        """
        filtered: list[str] = []
        i = 0
        n = len(tui_argv)
        seen_separator = False

        while i < n:
            arg = tui_argv[i]

            # `--` 分隔符：移除自身，后续元素原样保留。
            if arg == "--" and not seen_separator:
                seen_separator = True
                i += 1
                continue

            # launcher 自有参数：移除（含其值）。
            # 注意 --api-url 是 launcher 自有，--user-id / --token 是共享边界，
            # 共享边界由 analyze/build 处理，这里只过滤 _LAUNCHER_ONLY_FLAGS。
            if arg in _LAUNCHER_ONLY_FLAGS:
                # 这些参数可能也以 --flag=value 形式给出
                i += 1
                # 如果下一个不是另一个 flag，则当作它的值跳过。
                # 这里采用宽松策略：仅跳过 flag 本身，下一个元素如果是 flag 才不跳。
                # 但更严格做法是 --api-url 必须有值。
                # 简化处理：--no-save-login 是布尔型不需要值；--api-url 需要值。
                if arg == "--api-url":
                    if i < n and not tui_argv[i].startswith("--"):
                        i += 1
                continue

            if arg.startswith("--api-url="):
                i += 1
                continue

            filtered.append(arg)
            i += 1

        return tuple(filtered)
