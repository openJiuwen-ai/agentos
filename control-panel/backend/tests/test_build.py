"""Unit tests for image_process/build.py."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


class TestBuildParams:
    @staticmethod
    def test_fields():
        from app.image_process.build import BuildParams

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
        from app.image_process.build import BuildResult

        r = BuildResult(
            image="opencode:1.0",
            image_digest="sha256:abc123",
            image_path="/tmp/opencode-1.0.tar.gz",
            base_image="agent-base:1.0",
        )
        assert r.image == "opencode:1.0"
        assert r.image_digest == "sha256:abc123"
        assert r.image_path == "/tmp/opencode-1.0.tar.gz"
        assert r.base_image == "agent-base:1.0"


class TestBuildError:
    @staticmethod
    def test_message():
        from app.image_process.build import BuildError

        e = BuildError("something went wrong")
        assert str(e) == "something went wrong"
        assert isinstance(e, Exception)


class TestReport:
    @staticmethod
    def test_calls_callback():
        from app.image_process.build import _report

        called = []

        async def cb(pct):
            called.append(pct)

        asyncio_run(_report(cb, 42))
        assert called == [42]

    @staticmethod
    def test_noop_when_none():
        from app.image_process.build import _report

        asyncio_run(_report(None, 99))  # should not raise


class TestBuild:
    @staticmethod
    def test_creates_workdir_and_copies_files():
        """build() should create work_dir, copy tgz and Dockerfile."""
        from app.image_process.build import BuildParams, BuildResult, build

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "out"
            installer = Path(tmp) / "test.tgz"
            installer.write_bytes(b"fake tgz")

            def _fake_save(image_name, agent_name, version, work_dir):
                oci_dir = work_dir / "oci"
                oci_dir.mkdir(parents=True, exist_ok=True)
                (oci_dir / "test-1.0.tar.gz").write_text("fake oci")

            with patch("app.image_process.build._builder") as mock_builder:
                mock_builder.build_image = AsyncMock()
                mock_builder.save_image = AsyncMock(
                    side_effect=_fake_save)
                mock_builder.get_image_id = AsyncMock(
                    return_value="sha256:abc123")

                result = asyncio_run(build(BuildParams(
                    task_id="task-1",
                    agent_name="test",
                    version="1.0",
                    installer_path=installer,
                    output_dir=output_dir,
                )))

            assert isinstance(result, BuildResult)
            assert result.image == "test:1.0"
            assert result.image_digest == "sha256:abc123"
            assert result.base_image == "agent-base:1.0"
            assert (output_dir / "test-1.0.tar.gz").exists()
            assert not (output_dir / "task-1").exists()

    @staticmethod
    def test_respects_work_dir_param():
        from app.image_process.build import BuildParams, build

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "out"
            work_dir = Path(tmp) / "custom-work"
            installer = Path(tmp) / "test.tgz"
            installer.write_bytes(b"fake tgz")

            with patch("app.image_process.build._builder") as mock_builder:
                mock_builder.build_image = AsyncMock()

                async def _fake_save(_, agent_name, version, work_dir):
                    (work_dir / "oci").mkdir(parents=True, exist_ok=True)
                    (work_dir / "oci" / f"{agent_name}-{version}.tar.gz").write_text("oci")

                mock_builder.save_image = AsyncMock(side_effect=_fake_save)
                mock_builder.get_image_id = AsyncMock(
                    return_value="sha256:xyz")

                asyncio_run(build(BuildParams(
                    task_id="t1", agent_name="x", version="2.0",
                    installer_path=installer,
                    output_dir=output_dir,
                    work_dir=work_dir,
                )))

            assert not work_dir.exists()

    @staticmethod
    def test_calls_progress():
        from app.image_process.build import BuildParams, build

        with tempfile.TemporaryDirectory() as tmp:
            installer = Path(tmp) / "test.tgz"
            installer.write_bytes(b"x" * 100)
            progress = []

            async def cb(pct):
                progress.append(pct)

            with patch("app.image_process.build._builder") as mock_builder:
                mock_builder.build_image = AsyncMock()

                async def _fake_save(_, agent_name, version, work_dir):
                    (work_dir / "oci").mkdir(parents=True, exist_ok=True)
                    (work_dir / "oci" / f"{agent_name}-{version}.tar.gz").write_text("oci")

                mock_builder.save_image = AsyncMock(side_effect=_fake_save)
                mock_builder.get_image_id = AsyncMock(
                    return_value="sha256:done")

                asyncio_run(build(BuildParams(
                    task_id="t", agent_name="a", version="1",
                    installer_path=installer,
                    output_dir=Path(tmp) / "out",
                    on_progress=cb,
                )))

            assert progress == [10, 50, 90]


    @staticmethod
    def test_shell_injection_blocked():
        from app.image_process.build import BuildError, BuildParams, build

        with tempfile.TemporaryDirectory() as tmp:
            installer = Path(tmp) / "test.tgz"
            installer.write_bytes(b"x")
            for bad in ("name;rm -rf /", "v$(whoami)", "1.0\nmalicious"):
                p = BuildParams(
                    task_id="t", agent_name=bad if "/" not in bad else "safe",
                    version=bad,
                    installer_path=installer,
                    output_dir=Path(tmp) / "out",
                )
                with pytest.raises(BuildError, match="invalid"):
                    asyncio_run(build(p))

    @staticmethod
    def test_build_error_wraps_unexpected():
        from app.image_process.build import BuildError, BuildParams, build

        with tempfile.TemporaryDirectory() as tmp:
            installer = Path(tmp) / "test.tgz"
            installer.write_bytes(b"x")

            with patch("app.image_process.build._builder") as mock_builder:
                mock_builder.build_image = AsyncMock(
                    side_effect=RuntimeError("boom"))

                with pytest.raises(BuildError, match="boom"):
                    asyncio_run(build(BuildParams(
                        task_id="t", agent_name="a", version="1",
                        installer_path=installer,
                        output_dir=Path(tmp) / "out",
                    )))
            # work_dir is cleaned up even on error
            assert not (Path(tmp) / "out" / "t").exists()


class TestAbstractBuilder:
    @staticmethod
    def test_cannot_instantiate():
        from app.image_process.build import AbstractBuilder
        with pytest.raises(TypeError):
            AbstractBuilder()


class TestDockerBuilder:
    @staticmethod
    def test_check_available_does_not_raise():
        from app.image_process.build import DockerBuilder

        async def run():
            b = DockerBuilder()
            ok = await b.check_available()
            assert isinstance(ok, bool)

        asyncio_run(run())


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)
