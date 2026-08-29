"""FactoryService: resolve Recipe, then validate / selectBase / execute."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.builder import BuildError, ImageRuntime, _runtime
from app.factory.models import BuildResult, FactoryError
from app.factory.recipe import Recipe
from app.factory.recipes.npm_tgz import NpmTgzOnBaseRecipe
from app.factory.registry import RecipeRegistry


class FactoryService:
    def __init__(self, registry: RecipeRegistry, runtime: ImageRuntime) -> None:
        self._registry = registry
        self._runtime = runtime

    async def build_from_path(
        self,
        package_path: Path,
        options: dict[str, Any] | None = None,
        *,
        request_id: str,
        on_progress: Any | None = None,
    ) -> BuildResult:
        recipe: Recipe = self._registry.resolve(package_path)
        manifest = recipe.validate(package_path)
        base = recipe.select_base(package_path, manifest)
        return await recipe.execute(
            package_path,
            base,
            options,
            request_id=request_id,
            on_progress=on_progress,
        )

    async def remove_loaded_image(self, tag: str) -> None:
        try:
            await self._runtime.remove(tag)
        except BuildError as exc:
            raise FactoryError(str(exc)) from exc


def create_default_factory() -> FactoryService:
    registry = RecipeRegistry()
    registry.register(NpmTgzOnBaseRecipe(_runtime))
    return FactoryService(registry, _runtime)
