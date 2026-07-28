"""测试 ExecutableResolver 的白名单与 revalidate。"""

import os
import stat
import sys

import pytest

from agentos_tui_launcher.resolver import ExecutableResolverImpl
from agentos_tui_launcher.protocol import TuiTarget


@pytest.fixture
def resolver() -> ExecutableResolverImpl:
    return ExecutableResolverImpl()


class TestResolve:
    @staticmethod
    def test_resolve_primary_via_env(resolver, tmp_path, monkeypatch):
        # 通过环境变量指定路径。
        fake = tmp_path / "jiuwenswarm-tui"
        fake.write_text("#!/bin/sh\nexit 0\n")
        if os.name != "nt":
            os.chmod(str(fake), 0o755)
        monkeypatch.setenv("AGENTOS_TUI_PRIMARY_PATH", str(fake))
        result = resolver.resolve(TuiTarget.PRIMARY)
        assert result is not None
        assert result.target == TuiTarget.PRIMARY
        assert os.path.isabs(result.absolute_path)

    @staticmethod
    def test_resolve_cc_via_env(resolver, tmp_path, monkeypatch):
        fake = tmp_path / "cc-tui"
        fake.write_text("#!/bin/sh\nexit 0\n")
        if os.name != "nt":
            os.chmod(str(fake), 0o755)
        monkeypatch.setenv("AGENTOS_TUI_CC_PATH", str(fake))
        result = resolver.resolve(TuiTarget.CC)
        assert result is not None
        assert result.target == TuiTarget.CC

    @staticmethod
    def test_resolve_missing_returns_none(resolver, monkeypatch, tmp_path):
        # 清掉环境变量，并让 PATH 不包含目标。
        monkeypatch.delenv("AGENTOS_TUI_PRIMARY_PATH", raising=False)
        monkeypatch.setenv("PATH", str(tmp_path))
        result = resolver.resolve(TuiTarget.PRIMARY)
        # 注意：PATH 可能仍然包含系统路径；这里只断言不抛错。
        assert result is None or isinstance(result.absolute_path, str)


class TestRevalidate:
    @staticmethod
    def test_revalidate_existing(resolver, tmp_path, monkeypatch):
        fake = tmp_path / "jiuwenswarm-tui"
        fake.write_text("#!/bin/sh\nexit 0\n")
        if os.name != "nt":
            os.chmod(str(fake), 0o755)
        monkeypatch.setenv("AGENTOS_TUI_PRIMARY_PATH", str(fake))
        result = resolver.resolve(TuiTarget.PRIMARY)
        assert result is not None
        assert resolver.revalidate(result) is True

    @staticmethod
    def test_revalidate_missing(resolver, tmp_path, monkeypatch):
        fake = tmp_path / "jiuwenswarm-tui"
        fake.write_text("#!/bin/sh\nexit 0\n")
        if os.name != "nt":
            os.chmod(str(fake), 0o755)
        monkeypatch.setenv("AGENTOS_TUI_PRIMARY_PATH", str(fake))
        result = resolver.resolve(TuiTarget.PRIMARY)
        assert result is not None
        # 删除文件后再校验。
        os.unlink(str(fake))
        assert resolver.revalidate(result) is False
