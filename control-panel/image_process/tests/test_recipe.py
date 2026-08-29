"""Tests for Recipe matching, validation, and registry resolve."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.factory.models import FactoryError
from app.factory.recipes.npm_tgz import NpmTgzOnBaseRecipe
from app.factory.registry import RecipeRegistry
from tests.conftest import write_npm_tgz


@pytest.fixture
def recipe() -> NpmTgzOnBaseRecipe:
    return NpmTgzOnBaseRecipe(runtime=MagicMock())


def test_matches_shape_and_platform(tmp_path: Path, recipe: NpmTgzOnBaseRecipe):
    # UploadGate stores all package kinds under a neutral extension; recipes
    # must recognize artifacts by content rather than the persisted filename.
    pkg = write_npm_tgz(tmp_path / "ok.artifact", name="demo-linux-x64")
    with patch(
        "app.factory.recipes.npm_tgz._host_platform",
        return_value=("linux", "x64", "gnu"),
    ):
        assert recipe.artifact_matches(pkg) is True
        assert recipe.matches(pkg) is True


def test_matches_false_on_platform_mismatch(tmp_path: Path, recipe: NpmTgzOnBaseRecipe):
    pkg = write_npm_tgz(tmp_path / "win.tgz", name="demo-win32-x64")
    with patch(
        "app.factory.recipes.npm_tgz._host_platform",
        return_value=("linux", "x64", "gnu"),
    ):
        assert recipe.artifact_matches(pkg) is True
        assert recipe.matches(pkg) is False


def test_matches_false_on_garbage(tmp_path: Path, recipe: NpmTgzOnBaseRecipe):
    junk = tmp_path / "x.bin"
    junk.write_bytes(b"not gzip")
    assert recipe.matches(junk) is False
    assert recipe.artifact_matches(junk) is False


def test_validate_strips_scope_and_platform(tmp_path: Path, recipe: NpmTgzOnBaseRecipe):
    pkg = write_npm_tgz(
        tmp_path / "ok.tgz",
        name="@scope/opencode-linux-x64",
        version="1.2.3",
        display_name="OpenCode",
        bin_entry="opencode",
    )
    manifest = recipe.validate(pkg)
    assert manifest.name == "opencode"
    assert manifest.version == "1.2.3"
    assert manifest.display_name == "OpenCode"
    assert manifest.os == "linux"
    assert manifest.arch == "x64"
    assert manifest.libc == "gnu"


def test_validate_does_not_require_or_infer_entrypoint(
    tmp_path: Path, recipe: NpmTgzOnBaseRecipe
):
    pkg = write_npm_tgz(
        tmp_path / "elf.tgz",
        name="mytool-linux-x64",
        bin_entry=None,
        elf_name="mytool",
    )
    manifest = recipe.validate(pkg)
    assert manifest.name == "mytool"


def test_validate_rejects_unsafe_tag(tmp_path: Path, recipe: NpmTgzOnBaseRecipe):
    pkg = write_npm_tgz(tmp_path / "bad.tgz", name="bad;name-linux-x64", bin_entry="x")
    with pytest.raises(FactoryError, match="invalid docker tag"):
        recipe.validate(pkg)


def test_resolve_unique_hit(tmp_path: Path, recipe: NpmTgzOnBaseRecipe):
    pkg = write_npm_tgz(tmp_path / "ok.tgz")
    registry = RecipeRegistry()
    registry.register(recipe)
    with patch(
        "app.factory.recipes.npm_tgz._host_platform",
        return_value=("linux", "x64", "gnu"),
    ):
        assert registry.resolve(pkg) is recipe


def test_resolve_platform_mismatch_message(tmp_path: Path, recipe: NpmTgzOnBaseRecipe):
    pkg = write_npm_tgz(tmp_path / "win.tgz", name="demo-win32-x64")
    registry = RecipeRegistry()
    registry.register(recipe)
    with patch(
        "app.factory.recipes.npm_tgz._host_platform",
        return_value=("linux", "x64", "gnu"),
    ):
        with pytest.raises(FactoryError, match="平台不匹配"):
            registry.resolve(pkg)


def test_resolve_unrecognized(tmp_path: Path, recipe: NpmTgzOnBaseRecipe):
    junk = tmp_path / "x.bin"
    junk.write_bytes(b"nope")
    registry = RecipeRegistry()
    registry.register(recipe)
    with pytest.raises(FactoryError, match="无法识别制品"):
        registry.resolve(junk)
