"""Tests for server.py — Inference Service API endpoints.

All external dependencies (Docker, filesystem, auth) are mocked.
"""

import json
import sys
from collections import namedtuple
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Helpers ──────────────────────────────────────────────────────────────

_TestCtx = namedtuple(
    "_TestCtx",
    ["client", "srv", "config_dir", "templates_dir", "user_templates_dir", "vllm_dir"],
)


def _build_app(tmp_path: Path) -> _TestCtx:
    """Build a TestClient with mocked dependencies.

    Must patch modules that server.py imports at module level before
    importing server itself.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    vllm_dir = config_dir / "vllm"
    vllm_dir.mkdir()
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    user_templates_dir = tmp_path / "user_templates"
    user_templates_dir.mkdir()

    # Write a default config
    default_config = {
        "model": {"weight_path": "", "model_path": "", "model_name": ""},
        "deploy": {"image": "", "npu_num": 0},
        "parallel": {
            "tensor_parallel_size": 1, "data_parallel_size": 1,
            "enable_expert_parallel": False, "gpu_memory_utilization": 0.9,
            "quantization": "",
        },
        "inference": {
            "max_model_len": 131072, "max_num_batched_tokens": 10240,
            "max_num_seqs": 64, "enforce_eager": True,
        },
        "format": {
            "tokenizer_mode": "auto", "tool_call_parser": "",
            "reasoning_parser": "", "trust_remote_code": True,
        },
        "ports": {
            "controller_port": 2026, "coordinator_infer_port": 1025,
            "coordinator_mgmt_port": 1030, "coordinator_obs_port": 1029,
            "node_manager_port": 3026, "base_port": 10000,
        },
    }
    (config_dir / "config.json").write_text(
        json.dumps(default_config, indent=4), encoding="utf-8"
    )

    # Force fresh import of server so patches take effect
    sys.modules.pop("server", None)

    import server as srv

    # Override path constants
    srv.SCRIPT_DIR = tmp_path
    srv.CONFIG_DIR = config_dir
    srv.TEMPLATES_DIR = templates_dir
    srv.USER_TEMPLATES_DIR = user_templates_dir
    srv.SIMPLIFIED_CONFIG = config_dir / "config.json"
    srv.USER_CONFIG_DIR = vllm_dir
    srv.ACTIVE_USER_CONFIG = vllm_dir / "user_config.json"

    # Mock auth dependency to always pass
    from auth import TokenData

    def _mock_require_admin():
        return TokenData(user_id="test", username="admin", role="admin")

    # Override require_admin in the router's dependencies
    from auth import require_admin
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(srv.vllm_router)

    # Override the dependency globally
    app.dependency_overrides[require_admin] = _mock_require_admin

    client = TestClient(app)
    return _TestCtx(client, srv, config_dir, templates_dir, user_templates_dir, vllm_dir)


# ── Config endpoints ─────────────────────────────────────────────────────


class TestGetConfig:
    @staticmethod
    def test_returns_config(tmp_path):
        client, srv, *_ = _build_app(tmp_path)
        resp = client.get("/inference/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "model" in data
        assert "parallel" in data

    @staticmethod
    def test_config_has_all_sections(tmp_path):
        client, *_ = _build_app(tmp_path)
        resp = client.get("/inference/config")
        data = resp.json()
        expected = {"model", "deploy", "parallel", "inference", "format", "ports"}
        assert set(data.keys()) == expected


class TestUpdateConfig:
    @staticmethod
    def test_merge_single_field(tmp_path):
        client, srv, config_dir, *_ = _build_app(tmp_path)
        resp = client.put(
            "/inference/config",
            json={"model": {"model_name": "DeepSeek-R1"}},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Verify persisted
        saved = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
        assert saved["model"]["model_name"] == "DeepSeek-R1"
        # Unchanged fields preserved
        assert saved["model"]["weight_path"] == ""

    @staticmethod
    def test_merge_multiple_sections(tmp_path):
        client, srv, config_dir, *_ = _build_app(tmp_path)
        resp = client.put(
            "/inference/config",
            json={
                "model": {"model_name": "Qwen3-8B"},
                "parallel": {"tensor_parallel_size": 4},
            },
        )
        assert resp.status_code == 200
        saved = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
        assert saved["model"]["model_name"] == "Qwen3-8B"
        assert saved["parallel"]["tensor_parallel_size"] == 4


# ── Template endpoints ───────────────────────────────────────────────────


class TestTemplates:
    @staticmethod
    def test_list_empty(tmp_path):
        client, *_ = _build_app(tmp_path)
        resp = client.get("/inference/templates")
        assert resp.status_code == 200
        assert resp.json()["templates"] == []

    @staticmethod
    def test_save_and_list(tmp_path):
        client, srv, config_dir, templates_dir, user_templates_dir, vllm_dir = _build_app(tmp_path)
        # Save current config as template
        resp = client.post(
            "/inference/templates",
            json={"name": "my-config", "description": "test template"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # List should show it
        resp = client.get("/inference/templates")
        templates = resp.json()["templates"]
        assert len(templates) == 1
        assert templates[0]["name"] == "my-config"
        assert templates[0]["source"] == "user"

    @staticmethod
    def test_get_template_content(tmp_path):
        client, srv, *_ = _build_app(tmp_path)
        # Save a template
        client.post(
            "/inference/templates",
            json={"name": "qwen3-32b", "description": "Qwen3 config"},
        )
        # Get its content
        resp = client.get("/inference/templates/qwen3-32b")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "qwen3-32b"
        assert "config" in data

    @staticmethod
    def test_get_nonexistent_template(tmp_path):
        client, *_ = _build_app(tmp_path)
        resp = client.get("/inference/templates/nonexistent")
        assert resp.status_code == 404

    @staticmethod
    def test_delete_user_template(tmp_path):
        client, srv, *_ = _build_app(tmp_path)
        # Save
        client.post(
            "/inference/templates",
            json={"name": "to-delete", "description": ""},
        )
        # Delete
        resp = client.delete("/inference/templates/to-delete")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Verify gone
        resp = client.get("/inference/templates/to-delete")
        assert resp.status_code == 404

    @staticmethod
    def test_name_validation(tmp_path):
        client, *_ = _build_app(tmp_path)
        # Empty name
        resp = client.post(
            "/inference/templates",
            json={"name": "", "description": ""},
        )
        assert resp.status_code == 400

    @staticmethod
    def test_duplicate_name(tmp_path):
        client, *_ = _build_app(tmp_path)
        client.post(
            "/inference/templates",
            json={"name": "dup", "description": ""},
        )
        resp = client.post(
            "/inference/templates",
            json={"name": "dup", "description": ""},
        )
        assert resp.status_code == 409


# ── Status / Health ──────────────────────────────────────────────────────


class TestStatus:
    @staticmethod
    def test_status_not_running(tmp_path):
        client, srv, *_ = _build_app(tmp_path)
        with patch.object(srv.ctl, "run_cmd", return_value=(1, "", "")):
            resp = client.get("/inference/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["container"] == "not running"


class TestHealth:
    @staticmethod
    def test_health_check(tmp_path):
        client, srv, *_ = _build_app(tmp_path)
        with patch.object(srv.ctl, "run_cmd", return_value=(0, "running", "")):
            resp = client.get("/inference/health")
            assert resp.status_code == 200
            assert resp.json()["healthy"] is True


# ── Auth enforcement ─────────────────────────────────────────────────────


class TestAuthEnforcement:
    """Verify that auth dependency is applied to endpoints."""

    @staticmethod
    def test_no_auth_token_returns_401(tmp_path):
        client, srv, *_ = _build_app(tmp_path)
        # Remove the dependency override
        from auth import require_admin
        client.app.dependency_overrides.pop(require_admin, None)
        resp = client.get("/inference/config")
        assert resp.status_code == 401
