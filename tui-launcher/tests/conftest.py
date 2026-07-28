"""共享 pytest fixtures。"""

import os
import shutil
import tempfile
from typing import Optional

import pytest

from agentos_tui_launcher.config import FileConfigStore
from agentos_tui_launcher.credential_store import MemoryCredentialStore


@pytest.fixture
def temp_config_dir(tmp_path, monkeypatch) -> str:
    """提供一个干净的临时配置目录。"""
    config_dir = str(tmp_path / "config")
    monkeypatch.setenv("AGENTOS_TUI_CONFIG_DIR", config_dir)
    return config_dir


@pytest.fixture
def config_store(temp_config_dir) -> FileConfigStore:
    return FileConfigStore()


@pytest.fixture
def memory_credential_store() -> MemoryCredentialStore:
    return MemoryCredentialStore()
