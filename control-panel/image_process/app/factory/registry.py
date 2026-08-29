"""Recipe registry: pick exactly one matching Recipe."""

from __future__ import annotations

from pathlib import Path

from app.factory.models import FactoryError
from app.factory.recipe import Recipe


class RecipeRegistry:
    def __init__(self) -> None:
        self._recipes: list[Recipe] = []

    def register(self, recipe: Recipe) -> None:
        self._recipes.append(recipe)

    def resolve(self, package_path: Path) -> Recipe:
        hits = [r for r in self._recipes if r.matches(package_path)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) >= 2:
            ids = ", ".join(r.recipe_id for r in hits)
            raise FactoryError(f"recipe overlap for {package_path}: {ids}")
        kinds = [r for r in self._recipes if r.artifact_matches(package_path)]
        if kinds:
            raise FactoryError("平台不匹配")
        raise FactoryError("无法识别制品")
