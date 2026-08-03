"""Unit tests for app.builder (promoted from control-panel backend)."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)


class TestBuildParams:
    @staticmethod
    def test_fields():
        from app.builder import BuildParams

        p = BuildParams(
            task_id="task-1",
            agent_name="test",
            version="1.0",
            installer_path=Path("/tmp/test.tgz"),
            output_dir=Path("/tmp/out"),
            on_progress=None,
            work_dir=Path("/tmp/work"),
        )
        assert p.task_id == "task-1"
        assert p.agent_name == "test"
        assert p.work_dir == Path("/tmp/work")


class TestBuildResult:
    @staticmethod
    def test_fields():
        from app.builder import BuildResult

        r = BuildResult(
            image="opencode:1.0",
            image_digest="sha256:abc123",
            image_path="/tmp/opencode-1.0.tar.gz",
            base_image="agent-base:1.0",
        )
        assert r.image == "opencode:1.0"
        assert r.base_image == "agent-base:1.0"


class TestBuild:
    @staticmethod
    def test_creates_output_and_progress():
        from app.builder import BuildParams, BuildResult, build

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "out"
            installer = Path(tmp) / "test.tgz"
            installer.write_bytes(b"fake tgz")
            progress: list[int] = []

            async def cb(pct: int):
                progress.append(pct)

            async def _fake_save(_, agent_name, version, work_dir):
                (work_dir / "oci").mkdir(parents=True, exist_ok=True)
                (work_dir / "oci" / f"{agent_name}-{version}.tar.gz").write_text("oci")

            with patch("app.builder._builder") as mock_builder:
                mock_builder.build_image = AsyncMock()
                mock_builder.save_image = AsyncMock(side_effect=_fake_save)
                mock_builder.get_image_id = AsyncMock(return_value="sha256:abc")

                result = asyncio_run(build(BuildParams(
                    task_id="task-1",
                    agent_name="test",
                    version="1.0",
                    installer_path=installer,
                    output_dir=output_dir,
                    on_progress=cb,
                )))

            assert isinstance(result, BuildResult)
            assert result.image == "test:1.0"
            assert (output_dir / "test-1.0.tar.gz").exists()
            assert progress == [10, 50, 90]

    @staticmethod
    def test_shell_injection_blocked():
        from app.builder import BuildError, BuildParams, build

        with tempfile.TemporaryDirectory() as tmp:
            installer = Path(tmp) / "test.tgz"
            installer.write_bytes(b"x")
            with pytest.raises(BuildError, match="invalid"):
                asyncio_run(build(BuildParams(
                    task_id="t",
                    agent_name="safe",
                    version="1.0;rm",
                    installer_path=installer,
                    output_dir=Path(tmp) / "out",
                )))
