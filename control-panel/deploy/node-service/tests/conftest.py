"""Shared fixtures for node-service tests."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure the node-service package is importable
sys.path.append(str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def sample_config():
    """A minimal valid config.json structure."""
    return {
        "model": {
            "weight_path": "/data/models",
            "model_path": "Qwen3-32B",
            "model_name": "Qwen3-32B",
        },
        "deploy": {
            "image": "",
            "npu_num": 8,
        },
        "parallel": {
            "tensor_parallel_size": 8,
            "data_parallel_size": 1,
            "enable_expert_parallel": False,
            "gpu_memory_utilization": 0.9,
            "quantization": "ascend",
        },
        "inference": {
            "max_model_len": 131072,
            "max_num_batched_tokens": 10240,
            "max_num_seqs": 64,
            "enforce_eager": True,
        },
        "format": {
            "tokenizer_mode": "auto",
            "tool_call_parser": "",
            "reasoning_parser": "",
            "trust_remote_code": True,
        },
        "ports": {
            "controller_port": 2026,
            "coordinator_infer_port": 1025,
            "coordinator_mgmt_port": 1030,
            "coordinator_obs_port": 1029,
            "node_manager_port": 3026,
            "base_port": 10000,
        },
    }


@pytest.fixture
def tmp_config_file(tmp_path, sample_config):
    """Write sample config to a temp file and return its path."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(sample_config, indent=4), encoding="utf-8")
    return config_file


@pytest.fixture
def mock_docker(monkeypatch):
    """Mock Docker commands used by inference_ctl."""
    mock_run = MagicMock(return_value=(0, "running", ""))
    monkeypatch.setattr("inference_ctl.run_cmd", mock_run)
    return mock_run
