"""测试 stdout handoff JSON 解析。"""

import pytest

from agentos_tui_launcher import errors
from agentos_tui_launcher.handoff import HandoffMessage, parse_handoff_stdout


class TestParseHandoffStdout:
    @staticmethod
    def test_valid_single_line():
        stdout = '{"action":"switch","content":"switch /help","parsed":"/help"}\n'
        msg = parse_handoff_stdout(stdout)
        assert msg.content == "switch /help"
        assert msg.parsed == "/help"

    @staticmethod
    def test_valid_without_trailing_newline():
        stdout = '{"action":"switch","content":"switch /help","parsed":"/help"}'
        msg = parse_handoff_stdout(stdout)
        assert msg.content == "switch /help"
        assert msg.parsed == "/help"

    @staticmethod
    def test_extracts_last_json_line_from_mixed_output():
        # 过渡期 TUI 可能向 stdout 输出渲染内容；解析器取最后一行 JSON。
        stdout = (
            "Rendering frame 1\n"
            "Rendering frame 2\n"
            '{"action":"switch","content":"switch xxx","parsed":"xxx"}\n'
        )
        msg = parse_handoff_stdout(stdout)
        assert msg.content == "switch xxx"
        assert msg.parsed == "xxx"

    @staticmethod
    def test_parsed_derived_from_content_when_missing():
        stdout = '{"action":"switch","content":"switch /help"}\n'
        msg = parse_handoff_stdout(stdout)
        assert msg.content == "switch /help"
        assert msg.parsed == "/help"

    @staticmethod
    def test_parsed_derived_with_multiple_spaces():
        stdout = '{"action":"switch","content":"switch  /help"}\n'
        msg = parse_handoff_stdout(stdout)
        assert msg.parsed == "/help"

    @staticmethod
    def test_parsed_empty_when_content_is_just_switch():
        stdout = '{"action":"switch","content":"switch"}\n'
        msg = parse_handoff_stdout(stdout)
        assert msg.content == "switch"
        assert msg.parsed == ""

    @staticmethod
    def test_empty_stdout_raises():
        with pytest.raises(errors.HandoffParseError):
            parse_handoff_stdout("")

    @staticmethod
    def test_whitespace_only_stdout_raises():
        with pytest.raises(errors.HandoffParseError):
            parse_handoff_stdout("   \n  \n")

    @staticmethod
    def test_no_json_line_raises():
        with pytest.raises(errors.HandoffParseError):
            parse_handoff_stdout("Rendering frame 1\nNo JSON here\n")

    @staticmethod
    def test_invalid_json_raises():
        with pytest.raises(errors.HandoffParseError):
            parse_handoff_stdout("{invalid json}\n")

    @staticmethod
    def test_wrong_action_raises():
        # action != "switch" 的 JSON 行被跳过；无有效行则报错。
        stdout = '{"action":"other","content":"xxx"}\n'
        with pytest.raises(errors.HandoffParseError):
            parse_handoff_stdout(stdout)

    @staticmethod
    def test_missing_content_raises():
        stdout = '{"action":"switch","parsed":"xxx"}\n'
        with pytest.raises(errors.HandoffParseError):
            parse_handoff_stdout(stdout)

    @staticmethod
    def test_non_object_json_raises():
        stdout = '[1, 2, 3]\n'
        with pytest.raises(errors.HandoffParseError):
            parse_handoff_stdout(stdout)

    @staticmethod
    def test_wrong_action_then_valid_line():
        stdout = (
            '{"action":"other","content":"xxx"}\n'
            '{"action":"switch","content":"switch ok","parsed":"ok"}\n'
        )
        msg = parse_handoff_stdout(stdout)
        assert msg.content == "switch ok"
        assert msg.parsed == "ok"

    @staticmethod
    def test_ansi_escape_before_json():
        """PTY 输出中 JSON 行前有 ANSI 光标隐藏序列。"""
        stdout = (
            "\x1b[?25l"  # 隐藏光标
            '{"action":"switch","content":"switch claude","parsed":"claude"}\n'
            "\x1b[?25h"  # 显示光标
        )
        msg = parse_handoff_stdout(stdout)
        assert msg.content == "switch claude"
        assert msg.parsed == "claude"

    @staticmethod
    def test_ansi_escape_in_pty_output():
        """PTY 模式下 TUI 渲染输出 + handoff JSON 混合。"""
        stdout = (
            "\x1b[2J\x1b[H"  # 清屏 + 光标归位
            "TUI rendering line 1\r\n"
            "\x1b[32mTUI rendering line 2\x1b[0m\r\n"
            '{"action":"switch","content":"switch claude","parsed":"claude"}\r\n'
        )
        msg = parse_handoff_stdout(stdout)
        assert msg.content == "switch claude"
        assert msg.parsed == "claude"

    @staticmethod
    def test_json_embedded_in_ansi():
        """JSON 被 ANSI 序列包裹（光标移动 + 颜色码）。"""
        stdout = (
            "\x1b[1;1H"  # 光标定位
            '{"action":"switch","content":"switch claude","parsed":"claude"}'
            "\x1b[0m"
        )
        msg = parse_handoff_stdout(stdout)
        assert msg.content == "switch claude"
        assert msg.parsed == "claude"
