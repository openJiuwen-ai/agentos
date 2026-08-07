"""测试 CLI 的参数解析、子命令分发和退出码映射。

使用 fake SessionService 和 fake TuiSupervisor 避免真实网络与子进程。
"""

import io
import os
from typing import Optional

import pytest

from agentos_tui_launcher.cli import LauncherCli, EXIT_OK, EXIT_USAGE, EXIT_EXECUTABLE
from agentos_tui_launcher import errors


class TestHelpAndVersion:
    @staticmethod
    def test_help_returns_zero(capsys):
        cli = LauncherCli()
        rc = cli.run(("--help",))
        assert rc == 0
        out = capsys.readouterr().out
        assert "Usage" in out

    @staticmethod
    def test_version_returns_zero(capsys):
        cli = LauncherCli()
        rc = cli.run(("--version",))
        assert rc == 0
        out = capsys.readouterr().out
        assert "agentos-tui" in out


class TestUnknownCommand:
    @staticmethod
    def test_unknown_subcommand_returns_usage(capsys):
        cli = LauncherCli()
        rc = cli.run(("nonexistent-command",))
        assert rc == EXIT_USAGE
        err = capsys.readouterr().err
        assert "Unknown command" in err

    @staticmethod
    def test_user_subcommand_not_supported(capsys):
        cli = LauncherCli()
        rc = cli.run(("user", "list"))
        assert rc == EXIT_USAGE
        err = capsys.readouterr().err
        assert "not supported" in err


class TestParseLauncherArgs:
    @staticmethod
    def test_gateway_url_space_separated():
        opts, tui_argv = LauncherCli.parse_launcher_args(
            ("--gateway-url", "https://gw.example.com", "--url", "ws://localhost")
        )
        assert opts.gateway_url == "https://gw.example.com"
        assert tui_argv == ("--url", "ws://localhost")

    @staticmethod
    def test_gateway_url_equal_separated():
        opts, _ = LauncherCli.parse_launcher_args(("--gateway-url=https://gw.example.com",))
        assert opts.gateway_url == "https://gw.example.com"

    @staticmethod
    def test_gateway_url_and_api_url_together():
        opts, tui_argv = LauncherCli.parse_launcher_args(
            (
                "--api-url", "https://api.example.com",
                "--gateway-url", "https://gw.example.com",
                "--url", "ws://localhost",
            )
        )
        assert opts.api_url == "https://api.example.com"
        assert opts.gateway_url == "https://gw.example.com"
        assert tui_argv == ("--url", "ws://localhost")

    @staticmethod
    def test_gateway_url_missing_value_raises():
        with pytest.raises(errors.UsageError):
            LauncherCli.parse_launcher_args(("--gateway-url",))

    @staticmethod
    def test_gateway_url_empty_value_raises():
        with pytest.raises(errors.UsageError):
            LauncherCli.parse_launcher_args(("--gateway-url=",))

    @staticmethod
    def test_api_url_space_separated():
        opts, tui_argv = LauncherCli.parse_launcher_args(
            ("--api-url", "https://api.example.com", "--url", "ws://localhost")
        )
        assert opts.api_url == "https://api.example.com"
        assert tui_argv == ("--url", "ws://localhost")

    @staticmethod
    def test_api_url_equal_separated():
        opts, _ = LauncherCli.parse_launcher_args(("--api-url=https://api.example.com",))
        assert opts.api_url == "https://api.example.com"

    @staticmethod
    def test_no_save_login_flag():
        opts, _ = LauncherCli.parse_launcher_args(("--no-save-login",))
        assert opts.no_save_login is True

    @staticmethod
    def test_separator_splits_args():
        opts, tui_argv = LauncherCli.parse_launcher_args(
            ("--api-url", "https://api.example.com", "--", "--user-id", "abc")
        )
        assert opts.api_url == "https://api.example.com"
        # `--` 之后的元素归 tui_argv。
        assert tui_argv == ("--user-id", "abc")

    @staticmethod
    def test_api_url_missing_value_raises():
        with pytest.raises(errors.UsageError):
            LauncherCli.parse_launcher_args(("--api-url",))


class TestMaskUserId:
    @staticmethod
    def test_short_user_id():
        from agentos_tui_launcher.cli import _mask_user_id
        masked = _mask_user_id("short")
        # 长度 <= 12 时返回前 4 位 + ...
        assert masked == "shor..."

    @staticmethod
    def test_long_user_id():
        from agentos_tui_launcher.cli import _mask_user_id
        long_id = "7d0f4fbe-1a87-4dd1-9e9a-3d6dfeceec53"
        masked = _mask_user_id(long_id)
        assert masked.startswith("7d0f4fbe")
        assert masked.endswith("ec53")
        assert "..." in masked
