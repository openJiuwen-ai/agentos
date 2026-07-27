"""Unit tests for thirdparty_agent schemas."""

from app.schemas.thirdparty_agent import (
    AgentInstallerUploadResult,
    BuildStatusResponse,
    BuildTaskRequest,
    BuildTaskResponse,
)


class TestBuildTaskRequest:
    @staticmethod
    def test_all_fields():
        r = BuildTaskRequest(
            agent_name="opencode",
            version="1.1.0",
            display_name="OpenCode v2",
            entrypoint="opencode",
        )
        assert r.agent_name == "opencode"
        assert r.version == "1.1.0"
        assert r.display_name == "OpenCode v2"
        assert r.entrypoint == "opencode"


class TestAgentInstallerUploadResult:
    @staticmethod
    def test_all_fields():
        r = AgentInstallerUploadResult(
            agent_name="opencode",
            version="1.0.0",
            display_name="OpenCode",
            entrypoint="opencode",
        )
        assert r.agent_name == "opencode"
        assert r.version == "1.0.0"


class TestBuildTaskResponse:
    @staticmethod
    def test_pending_creation():
        r = BuildTaskResponse(task_id="build-abc123", status="pending")
        assert r.task_id == "build-abc123"
        assert r.status == "pending"
        assert r.created_at is None


class TestBuildStatusResponse:
    @staticmethod
    def test_done():
        from datetime import datetime, timezone

        now = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 7, 15, 12, 5, 0, tzinfo=timezone.utc)
        r = BuildStatusResponse(
            task_id="build-abc", status="done", progress=100,
            image="opencode:1.0.0", image_digest="sha256:abc",
            started_at=now, finished_at=end,
            registered=True,
        )
        assert r.status == "done"
        assert r.progress == 100
        assert r.registered is True
        assert r.image == "opencode:1.0.0"

    @staticmethod
    def test_failed():
        r = BuildStatusResponse(task_id="build-abc", status="failed")
        assert r.status == "failed"
        assert r.registered is False
        assert r.progress == 0

    @staticmethod
    def test_building():
        r = BuildStatusResponse(
            task_id="build-abc", status="building", progress=42,
        )
        assert r.status == "building"
        assert r.progress == 42
        assert r.registered is False
