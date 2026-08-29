"""Unit tests for recipe execute() with a mocked ImageRuntime."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.factory.models import BaseRef, BuildResult
from app.factory.recipes.npm_tgz import NpmTgzOnBaseRecipe
from tests.conftest import write_npm_tgz


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


def _runtime_mock() -> MagicMock:
    runtime = MagicMock()
    runtime.inspect = AsyncMock(
        return_value={
            "id": "sha256:abc",
            "labels": {},
            "runtime_spec": {"runtime": "python3.11"},
        }
    )
    runtime.get_sandbox_type = AsyncMock(return_value="docker")
    runtime.build = AsyncMock()

    async def _save(tag, dest: Path):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("oci")

    runtime.save_archive = AsyncMock(side_effect=_save)
    return runtime


class TestExecute:
    @staticmethod
    def test_creates_archive_and_progress(tmp_path: Path, monkeypatch):
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
        from app.config import settings

        settings.OUTPUT_DIR = str(tmp_path / "out")
        settings.WORK_DIR = str(tmp_path / "work")
        settings.THIRDPARTY_AGENT_ARCHIVE_ENABLED = True

        pkg = write_npm_tgz(tmp_path / "demo-linux-x64.tgz")
        runtime = _runtime_mock()
        recipe = NpmTgzOnBaseRecipe(runtime)
        progress: list[int] = []

        async def cb(pct: int):
            progress.append(pct)

        result = asyncio_run(
            recipe.execute(
                pkg,
                BaseRef(ref="agent-base:1.0"),
                {},
                request_id="task-1",
                on_progress=cb,
            )
        )

        assert isinstance(result, BuildResult)
        assert result.image_ref == "demo:1.0.0"
        assert result.recipe_id == "npm_tgz_on_base"
        assert result.base_ref == "agent-base:1.0"
        assert Path(result.archive_path).exists()
        assert progress == [10, 50, 90]
        build_args = runtime.build.call_args.args[2]
        assert build_args["AGENTOS_SYS_UID"] == "1000"
        assert build_args["BASE_IMAGE"] == "agent-base:1.0"

    @staticmethod
    def test_archive_disabled_by_default(tmp_path: Path):
        from app.config import settings

        settings.OUTPUT_DIR = str(tmp_path / "out")
        settings.WORK_DIR = str(tmp_path / "work")
        settings.THIRDPARTY_AGENT_ARCHIVE_ENABLED = False
        pkg = write_npm_tgz(tmp_path / "demo-linux-x64.tgz")
        runtime = _runtime_mock()

        result = asyncio_run(
            NpmTgzOnBaseRecipe(runtime).execute(
                pkg,
                BaseRef(ref="agent-base:1.0"),
                {},
                request_id="no-archive",
            )
        )

        assert result.archive_path is None
        runtime.save_archive.assert_not_awaited()

    @staticmethod
    def test_uid_from_env(tmp_path: Path, monkeypatch):
        monkeypatch.setenv("AGENTOS_SYS_UID", "2001")
        monkeypatch.setenv("AGENTOS_SYS_GID", "2002")
        from app.config import settings

        settings.OUTPUT_DIR = str(tmp_path / "out")
        settings.WORK_DIR = str(tmp_path / "work")

        pkg = write_npm_tgz(tmp_path / "demo-linux-x64.tgz")
        runtime = _runtime_mock()
        recipe = NpmTgzOnBaseRecipe(runtime)
        asyncio_run(
            recipe.execute(
                pkg,
                BaseRef(ref="agent-base:1.0"),
                {},
                request_id="t",
            )
        )
        build_args = runtime.build.call_args.args[2]
        assert build_args["AGENTOS_SYS_UID"] == "2001"
        assert build_args["AGENTOS_SYS_GID"] == "2002"

    @staticmethod
    def test_runtime_spec_from_base(tmp_path: Path):
        from app.config import settings

        settings.OUTPUT_DIR = str(tmp_path / "out")
        settings.WORK_DIR = str(tmp_path / "work")
        pkg = write_npm_tgz(tmp_path / "demo-linux-x64.tgz")
        runtime = _runtime_mock()
        recipe = NpmTgzOnBaseRecipe(runtime)
        result = asyncio_run(
            recipe.execute(
                pkg,
                BaseRef(ref="agent-base:1.0"),
                {},
                request_id="t",
            )
        )
        assert result.runtime_spec == {
            "runtime": "python3.11",
            "sandbox_type": "docker",
        }
