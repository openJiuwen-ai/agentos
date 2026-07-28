"""stdout handoff JSON 解析。

新设计（tui-switch-cc-design-new.md 第 10.2/10.3 节）下，JiuwenSwarm TUI 在退出前
向 stdout 输出一行 JSON 格式的 handoff 消息：

    {"action":"switch","content":"switch xxx","parsed":"xxx"}\n

launcher 在子进程退出后从 stdout 管道读取该消息，解析 `content` 和 `parsed` 字段，
然后通过 gateway WS + SSH 隧道完成切换。

stdout 理论上只应包含这一行 JSON，但为了兼容过渡期（TUI 仍向 stdout 输出渲染内容），
解析器会从捕获的 stdout 中查找最后一行符合 handoff JSON 格式的内容。

PTY 模式下 stdout 会包含大量 ANSI 转义序列（光标移动、颜色码、清屏等），
解析器会先剥离这些转义序列，再查找 handoff JSON。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from . import errors


# ANSI 转义序列正则：匹配 CSI（\x1b[...）、OSC（\x1b]...\x07）、
# 光标可见性（\x1b[?25l/h）等常见序列。
_ANSI_ESCAPE_RE = re.compile(
    r"\x1b\[[0-9;?]*[a-zA-Z]"  # CSI 序列：\x1b[...m, \x1b[...H, \x1b[?25l 等
    r"|\x1b\][^\x07]*\x07"      # OSC 序列：\x1b]...BEL
    r"|\x1b[()][AB012]"         # 字符集选择
    r"|\x1b[=>]"                # 键盘模式
    r"|\x1b[78]"                # 保存/恢复光标
)


@dataclass(frozen=True)
class HandoffMessage:
    """从子进程 stdout 解析出的 handoff 消息。

    - `content`：完整命令内容，如 "switch xxx"。
    - `parsed`：解析后的参数，如 "xxx"；若 TUI 未提供则从 content 中提取。
    """

    content: str
    parsed: str


def parse_handoff_stdout(stdout: str) -> HandoffMessage:
    """从子进程 stdout 中解析 handoff JSON 消息。

    解析步骤：
    1. 剥离 ANSI 转义序列（PTY 模式下 stdout 包含大量转义序列）
    2. 规范化换行符（\\r\\n / \\r → \\n）
    3. 逐行从后向前查找 handoff JSON
    4. 若逐行查找失败，用 regex 在整个输出中搜索 JSON 模式作为兜底

    Raises:
        HandoffParseError: stdout 为空、未找到 handoff JSON 或 JSON 格式错误。
    """
    if not stdout or not stdout.strip():
        raise errors.HandoffParseError("子进程 stdout 为空，未找到 handoff 消息。")

    # 1. 剥离 ANSI 转义序列
    cleaned = _ANSI_ESCAPE_RE.sub("", stdout)

    # 2. 规范化换行符
    normalized = cleaned.replace("\r\n", "\n").replace("\r", "\n")

    # 3. 逐行从后向前查找
    lines = normalized.strip().splitlines()
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped or not stripped.startswith("{"):
            continue
        msg = _try_parse_json_line(stripped)
        if msg is not None:
            return msg

    # 4. 兜底：用 regex 在整个输出中搜索 handoff JSON 模式
    # 处理 JSON 被拆分或嵌入其他文本的情况
    json_pattern = re.compile(
        r'\{"action"\s*:\s*"switch"[^}]*\}'
    )
    matches = json_pattern.findall(normalized)
    for match in reversed(matches):
        msg = _try_parse_json_line(match)
        if msg is not None:
            return msg

    raise errors.HandoffParseError(
        "子进程 stdout 中未找到有效的 handoff JSON 消息。"
    )


def _try_parse_json_line(line: str) -> Optional[HandoffMessage]:
    """尝试解析单行 JSON 为 HandoffMessage。

    要求 action == "switch" 且 content 非空。
    parsed 缺失时从 content 中提取（去掉 "switch " 前缀）。
    """
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None
    if data.get("action") != "switch":
        return None

    content = data.get("content")
    if not isinstance(content, str) or not content:
        return None

    parsed = data.get("parsed")
    if not isinstance(parsed, str) or not parsed:
        # parsed 缺失时从 content 提取：去掉 "switch " 前缀。
        parsed = _extract_parsed_from_content(content)

    return HandoffMessage(content=content, parsed=parsed)


def _extract_parsed_from_content(content: str) -> str:
    """从 "switch xxx" 内容中提取 "xxx" 部分。

    支持以下格式：
    - "switch xxx" -> "xxx"
    - "switch  xxx" -> "xxx"（多空格）
    - "switch" -> ""（无参数）
    """
    # 去掉 "switch" 前缀和前后空白。
    if content.startswith("switch"):
        rest = content[len("switch"):].strip()
        return rest
    # 不以 switch 开头时返回完整内容。
    return content.strip()
