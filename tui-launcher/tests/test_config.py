"""测试 FileConfigStore 的读写与原子性。"""

import json
import os

import pytest

from agentos_tui_launcher import errors
from agentos_tui_launcher.config import ClientConfig, FileConfigStore


class TestLoad:
    @staticmethod
    def test_missing_file_returns_default(config_store):
        cfg = config_store.load()
        assert cfg.api_url is None
        assert cfg.last_user_id is None
        assert cfg.allow_insecure_http is False

    @staticmethod
    def test_loads_existing_config(config_store, temp_config_dir):
        os.makedirs(temp_config_dir, exist_ok=True)
        path = os.path.join(temp_config_dir, "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "api_url": "https://agentos.example.com",
                    "last_user_id": "user-1",
                    "last_username": "alice",
                },
                f,
            )
        cfg = config_store.load()
        assert cfg.api_url == "https://agentos.example.com"
        assert cfg.last_user_id == "user-1"
        assert cfg.last_username == "alice"
        assert cfg.allow_insecure_http is False

    @staticmethod
    def test_corrupted_file_raises_config_error(config_store, temp_config_dir):
        os.makedirs(temp_config_dir, exist_ok=True)
        path = os.path.join(temp_config_dir, "config.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{invalid json")
        with pytest.raises(errors.ConfigError):
            config_store.load()


class TestSave:
    @staticmethod
    def test_save_and_load_roundtrip(config_store):
        cfg = ClientConfig(
            api_url="https://agentos.example.com",
            websocket_url="wss://agentos.example.com/tui",
            last_user_id="user-1",
            last_username="alice",
            allow_insecure_http=False,
        )
        config_store.save(cfg)
        loaded = config_store.load()
        assert loaded.api_url == cfg.api_url
        assert loaded.websocket_url == cfg.websocket_url
        assert loaded.last_user_id == cfg.last_user_id
        assert loaded.last_username == cfg.last_username
        assert loaded.allow_insecure_http == cfg.allow_insecure_http

    @staticmethod
    def test_save_creates_directory(config_store, temp_config_dir):
        # 目录初始不存在。
        assert not os.path.exists(temp_config_dir)
        cfg = ClientConfig(
            api_url=None,
            websocket_url=None,
            last_user_id=None,
            last_username=None,
        )
        config_store.save(cfg)
        assert os.path.exists(temp_config_dir)

    @staticmethod
    def test_save_none_filtered(config_store):
        cfg = ClientConfig(
            api_url=None,
            websocket_url=None,
            last_user_id=None,
            last_username=None,
        )
        config_store.save(cfg)
        # 即使所有字段都是 None，也应该能 round-trip。
        loaded = config_store.load()
        assert loaded.api_url is None
