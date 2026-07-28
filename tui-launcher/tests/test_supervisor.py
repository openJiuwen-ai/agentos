"""测试 TuiSupervisor 的启动、handoff 和退出码透传。

使用 fake ProcessRunner 避免 actually 启动子进程。
新设计下不再有 run_cc；SWITCH_CC 的后续处理由 CLI 层完成。
"""

import pytest

from agentos_tui_launcher.protocol import (
    HandoffAction,
    REAUTH_EXIT_CODE,
    SWITCH_CC_EXIT_CODE,
)
from agentos_tui_launcher.resolver import ResolvedExecutable
from agentos_tui_launcher.protocol import TuiTarget
from agentos_tui_launcher.supervisor import (
    ProcessResult,
    ProcessSpec,
    ProcessRunner,
    SupervisedProcessResult,
    SupervisionProtocol,
    TuiSupervisor,
)


# ============================================================================
# Fake 依赖
# ============================================================================


class FakeRunner(ProcessRunner):
    """按预设脚本返回退出码和 stdout 的 ProcessRunner。"""

    def __init__(
        self,
        exit_codes: list[int],
        stdout_values: list[str] | None = None,
    ) -> None:
        self._exit_codes = list(exit_codes)
        self._stdout_values = list(stdout_values) if stdout_values else []
        self.calls: list[ProcessSpec] = []
        self.forward_count = 0

    def run_foreground(self, spec: ProcessSpec) -> ProcessResult:
        self.calls.append(spec)
        if not self._exit_codes:
            return ProcessResult(exit_code=0)
        exit_code = self._exit_codes.pop(0)
        stdout = (
            self._stdout_values.pop(0)
            if self._stdout_values
            else ""
        )
        return ProcessResult(exit_code=exit_code, stdout=stdout)

    def forward_termination(self) -> None:
        self.forward_count += 1


class FakeResolver:
    """总是返回 True 的 revalidate。"""

    @staticmethod
    def revalidate(executable: ResolvedExecutable) -> bool:
        return True

    @staticmethod
    def resolve(target):
        return ResolvedExecutable(target=target, absolute_path=f"/fake/{target.value}")


@pytest.fixture
def primary_executable() -> ResolvedExecutable:
    return ResolvedExecutable(
        target=TuiTarget.PRIMARY, absolute_path="/fake/jiuwenswarm-tui"
    )


@pytest.fixture
def supervisor() -> TuiSupervisor:
    return TuiSupervisor(
        runner=FakeRunner([0]),
        protocol=SupervisionProtocol(),
        resolver=FakeResolver(),
    )


# ============================================================================
# run_primary
# ============================================================================


class TestRunPrimary:
    @staticmethod
    def test_normal_exit_returns_action_none(supervisor, primary_executable):
        result = supervisor.run_primary(
            primary=primary_executable,
            primary_argv=("--url", "ws://localhost"),
            reauth_enabled=True,
            base_env={"PATH": "/usr/bin"},
            cwd="/tmp",
        )
        assert result.action is None
        assert result.exit_code == 0

    @staticmethod
    def test_switch_cc_action(supervisor, primary_executable):
        supervisor.runner = FakeRunner([SWITCH_CC_EXIT_CODE])
        result = supervisor.run_primary(
            primary=primary_executable,
            primary_argv=(),
            reauth_enabled=True,
            base_env={},
            cwd="/tmp",
        )
        assert result.action == HandoffAction.SWITCH_CC

    @staticmethod
    def test_switch_cc_captures_stdout(supervisor, primary_executable):
        stdout_line = '{"content": "switch to cc", "parsed": "/help"}'
        supervisor.runner = FakeRunner(
            [SWITCH_CC_EXIT_CODE],
            stdout_values=[stdout_line],
        )
        result = supervisor.run_primary(
            primary=primary_executable,
            primary_argv=(),
            reauth_enabled=True,
            base_env={},
            cwd="/tmp",
        )
        assert result.action == HandoffAction.SWITCH_CC
        assert result.stdout == stdout_line

    @staticmethod
    def test_reauth_action_when_enabled(supervisor, primary_executable):
        supervisor.runner = FakeRunner([REAUTH_EXIT_CODE])
        result = supervisor.run_primary(
            primary=primary_executable,
            primary_argv=(),
            reauth_enabled=True,
            base_env={},
            cwd="/tmp",
        )
        assert result.action == HandoffAction.REAUTH_REQUIRED

    @staticmethod
    def test_reauth_not_action_when_disabled(supervisor, primary_executable):
        # 显式模式：89 按普通退出码透传。
        supervisor.runner = FakeRunner([REAUTH_EXIT_CODE])
        result = supervisor.run_primary(
            primary=primary_executable,
            primary_argv=(),
            reauth_enabled=False,
            base_env={},
            cwd="/tmp",
        )
        assert result.action is None
        assert result.exit_code == REAUTH_EXIT_CODE

    @staticmethod
    def test_injects_protocol_env(supervisor, primary_executable):
        supervisor.run_primary(
            primary=primary_executable,
            primary_argv=(),
            reauth_enabled=True,
            base_env={"EXISTING": "value"},
            cwd="/tmp",
        )
        spec: ProcessSpec = supervisor.runner.calls[0]  # type: ignore[attr-defined]
        assert spec.env["AGENTOS_TUI_SUPERVISED"] == "1"
        assert spec.env["AGENTOS_TUI_SWITCH_CC_EXIT_CODE"] == "88"
        assert spec.env["AGENTOS_TUI_REAUTH_EXIT_CODE"] == "89"
        # AGENTOS_CC_TUI_EXECUTABLE 必须注入（TUI 端 checkHandoff 预检要求）
        assert "AGENTOS_CC_TUI_EXECUTABLE" in spec.env
        # 原环境保留。
        assert spec.env["EXISTING"] == "value"

    @staticmethod
    def test_cc_tui_executable_uses_preset_value(supervisor, primary_executable):
        """base_env 中预设的 AGENTOS_CC_TUI_EXECUTABLE 应被保留。"""
        supervisor.run_primary(
            primary=primary_executable,
            primary_argv=(),
            reauth_enabled=False,
            base_env={"AGENTOS_CC_TUI_EXECUTABLE": "/custom/cc-tui"},
            cwd="/tmp",
        )
        spec: ProcessSpec = supervisor.runner.calls[0]  # type: ignore[attr-defined]
        assert spec.env["AGENTOS_CC_TUI_EXECUTABLE"] == "/custom/cc-tui"

    @staticmethod
    def test_cc_tui_executable_defaults_when_missing(supervisor, primary_executable):
        """base_env 中没有 AGENTOS_CC_TUI_EXECUTABLE 时用占位值。"""
        supervisor.run_primary(
            primary=primary_executable,
            primary_argv=(),
            reauth_enabled=False,
            base_env={},
            cwd="/tmp",
        )
        spec: ProcessSpec = supervisor.runner.calls[0]  # type: ignore[attr-defined]
        assert "AGENTOS_CC_TUI_EXECUTABLE" in spec.env
        assert spec.env["AGENTOS_CC_TUI_EXECUTABLE"]  # 非空


# ============================================================================
# run (兼容入口)
# ============================================================================


class TestRunCompat:
    @staticmethod
    def test_run_normal_exit(supervisor, primary_executable):
        supervisor.runner = FakeRunner([0])
        exit_code = supervisor.run(
            primary=primary_executable,
            primary_argv=(),
            base_env={},
            cwd="/tmp",
        )
        assert exit_code == 0

    @staticmethod
    def test_run_switch_cc_passthrough_exit_code(supervisor, primary_executable):
        # 兼容入口中 88 按普通退出码透传（不执行 gateway + SSH 流程）。
        supervisor.runner = FakeRunner([SWITCH_CC_EXIT_CODE])
        exit_code = supervisor.run(
            primary=primary_executable,
            primary_argv=(),
            base_env={},
            cwd="/tmp",
        )
        assert exit_code == SWITCH_CC_EXIT_CODE

    @staticmethod
    def test_run_reauth_in_compat_mode_passthrough(supervisor, primary_executable):
        # 兼容入口中 89 按普通退出码透传。
        supervisor.runner = FakeRunner([REAUTH_EXIT_CODE])
        exit_code = supervisor.run(
            primary=primary_executable,
            primary_argv=(),
            base_env={},
            cwd="/tmp",
        )
        assert exit_code == REAUTH_EXIT_CODE
