"""Unit tests for agent_metrics_config — VictoriaMetrics agent-metrics.json sync."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import agent_metrics_config as amc


@pytest.fixture
def metrics_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_path = tmp_path / "agent-metrics.json"
    monkeypatch.setattr(amc, "get_config_path", lambda: config_path)
    return config_path


class TestNormalizeTarget:
    @staticmethod
    def test_host_port_passthrough():
        assert amc.normalize_target("141.1.1.1:9000") == "141.1.1.1:9000"

    @staticmethod
    def test_strips_url_scheme_and_path():
        assert amc.normalize_target("https://141.1.1.1:9000/v1") == "141.1.1.1:9000"

    @staticmethod
    def test_empty_raises():
        with pytest.raises(amc.AgentMetricsConfigError):
            amc.normalize_target("  ")


class TestBuildEntry:
    @staticmethod
    def test_format():
        entry = amc.build_entry("vllm", "141.1.1.1:9000")
        assert entry == {
            "targets": ["141.1.1.1:9000"],
            "labels": {"job": "vllm-141.1.1.1:9000"},
        }

    @staticmethod
    def test_engine_normalized_to_lowercase():
        entry = amc.build_entry("vLLM", "141.1.1.1:9000")
        assert entry["labels"]["job"] == "vllm-141.1.1.1:9000"
        assert amc.build_job("SGLang", "10.0.0.1:8000") == "sglang-10.0.0.1:8000"


class TestAddEntry:
    @staticmethod
    def test_creates_file(metrics_file: Path):
        job = amc.add_entry("vllm", "141.1.1.1:9000")
        assert job == "vllm-141.1.1.1:9000"
        data = json.loads(metrics_file.read_text(encoding="utf-8"))
        assert data == [{
            "targets": ["141.1.1.1:9000"],
            "labels": {"job": "vllm-141.1.1.1:9000"},
        }]

    @staticmethod
    def test_duplicate_job_is_idempotent(metrics_file: Path):
        job1 = amc.add_entry("vllm", "141.1.1.1:9000")
        job2 = amc.add_entry("vllm", "141.1.1.1:9000")
        assert job1 == job2 == "vllm-141.1.1.1:9000"
        data = json.loads(metrics_file.read_text(encoding="utf-8"))
        assert len(data) == 1

    @staticmethod
    def test_appends_to_existing(metrics_file: Path):
        metrics_file.write_text(
            json.dumps([{
                "targets": ["10.0.0.1:8000"],
                "labels": {"job": "other-10.0.0.1:8000"},
            }]),
            encoding="utf-8",
        )
        amc.add_entry("vllm", "141.1.1.1:9000")
        data = json.loads(metrics_file.read_text(encoding="utf-8"))
        assert len(data) == 2


class TestUpdateEntry:
    @staticmethod
    def test_updates_job_and_target(metrics_file: Path):
        amc.add_entry("vllm", "141.1.1.1:9000")
        new_job = amc.update_entry(
            "vllm-141.1.1.1:9000", "vllm2", "142.2.2.2:9100",
        )
        assert new_job == "vllm2-142.2.2.2:9100"
        data = json.loads(metrics_file.read_text(encoding="utf-8"))
        assert data == [{
            "targets": ["142.2.2.2:9100"],
            "labels": {"job": "vllm2-142.2.2.2:9100"},
        }]


class TestRemoveEntry:
    @staticmethod
    def test_remove_by_job(metrics_file: Path):
        amc.add_entry("vllm", "141.1.1.1:9000")
        removed = amc.remove_entry("vllm-141.1.1.1:9000")
        assert removed is True
        assert json.loads(metrics_file.read_text(encoding="utf-8")) == []

    @staticmethod
    def test_remove_missing_returns_false(metrics_file: Path):
        metrics_file.write_text("[]", encoding="utf-8")
        assert amc.remove_entry("missing-job") is False
