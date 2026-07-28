"""测试 SupervisionProtocol 的环境构造与退出码分类。"""

import pytest

from agentos_tui_launcher.protocol import (
    ENV_REAUTH_EXIT_CODE,
    ENV_SUPERVISED,
    ENV_SUPERVISED_VALUE,
    ENV_SWITCH_CC_EXIT_CODE,
    HandoffAction,
    ProtocolSnapshot,
    REAUTH_EXIT_CODE,
    SWITCH_CC_EXIT_CODE,
    strip_protocol_env,
)
from agentos_tui_launcher.supervisor import SupervisionProtocol


@pytest.fixture
def protocol() -> SupervisionProtocol:
    return SupervisionProtocol()


# ============================================================================
# build_primary_env
# ============================================================================


class TestBuildPrimaryEnv:
    @staticmethod
    def test_includes_supervised_and_switch_cc(protocol):
        env = protocol.build_primary_env({}, reauth_enabled=False)
        assert env[ENV_SUPERVISED] == ENV_SUPERVISED_VALUE
        assert env[ENV_SWITCH_CC_EXIT_CODE] == str(SWITCH_CC_EXIT_CODE)

    @staticmethod
    def test_reauth_disabled_no_reauth_env(protocol):
        env = protocol.build_primary_env({}, reauth_enabled=False)
        assert ENV_REAUTH_EXIT_CODE not in env

    @staticmethod
    def test_reauth_enabled_sets_reauth_env(protocol):
        env = protocol.build_primary_env({}, reauth_enabled=True)
        assert env[ENV_REAUTH_EXIT_CODE] == str(REAUTH_EXIT_CODE)

    @staticmethod
    def test_no_token_in_env(protocol):
        env = protocol.build_primary_env(
            {"EXISTING": "value"}, reauth_enabled=True
        )
        # 确保不会无意中包含敏感字段。
        assert "ACCESS_TOKEN" not in env
        assert "REFRESH_TOKEN" not in env
        assert "PASSWORD" not in env
        # 原有环境保留。
        assert env["EXISTING"] == "value"


# ============================================================================
# make_snapshot + classify_exit
# ============================================================================


class TestClassifyExit:
    @staticmethod
    def test_switch_cc_action(protocol):
        snapshot = protocol.make_snapshot(reauth_enabled=True)
        action = protocol.classify_exit(SWITCH_CC_EXIT_CODE, snapshot)
        assert action == HandoffAction.SWITCH_CC

    @staticmethod
    def test_reauth_action_when_enabled(protocol):
        snapshot = protocol.make_snapshot(reauth_enabled=True)
        action = protocol.classify_exit(REAUTH_EXIT_CODE, snapshot)
        assert action == HandoffAction.REAUTH_REQUIRED

    @staticmethod
    def test_reauth_not_action_when_disabled(protocol):
        # 显式模式：reauth_exit_code 为 None，89 按普通退出码处理。
        snapshot = protocol.make_snapshot(reauth_enabled=False)
        action = protocol.classify_exit(REAUTH_EXIT_CODE, snapshot)
        assert action is None

    @staticmethod
    def test_normal_exit_code_no_action(protocol):
        snapshot = protocol.make_snapshot(reauth_enabled=True)
        assert protocol.classify_exit(0, snapshot) is None
        assert protocol.classify_exit(1, snapshot) is None
        assert protocol.classify_exit(70, snapshot) is None


# ============================================================================
# strip_protocol_env
# ============================================================================


class TestStripProtocolEnv:
    @staticmethod
    def test_strips_all_protocol_vars():
        env = {
            ENV_SUPERVISED: "1",
            ENV_SWITCH_CC_EXIT_CODE: "88",
            ENV_REAUTH_EXIT_CODE: "89",
            "PATH": "/usr/bin",
        }
        result = strip_protocol_env(env)
        assert ENV_SUPERVISED not in result
        assert ENV_SWITCH_CC_EXIT_CODE not in result
        assert ENV_REAUTH_EXIT_CODE not in result
        assert "PATH" in result

    @staticmethod
    def test_keeps_unrelated_env():
        env = {"HOME": "/home/user", "PATH": "/usr/bin"}
        result = strip_protocol_env(env)
        assert result == env
