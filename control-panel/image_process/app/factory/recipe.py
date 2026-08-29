"""Recipe interface: one build strategy."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.factory.models import ArtifactManifest, BaseRef, BuildResult


class Recipe(ABC):
    """A build plan. Constants are class attributes, not caller input."""

    recipe_id: str
    artifact_kind: str
    inject_ssh: bool
    inject_yuanrong_sdk: bool
    assemble: str

    def artifact_matches(self, package_path: Path) -> bool:
        """Shape-only recognition (no platform). Used by resolve() diagnostics."""
        return False

    @abstractmethod
    def matches(self, package_path: Path) -> bool:
        """Shape + platform. Must not raise; I/O errors are false."""

    @abstractmethod
    def validate(self, package_path: Path) -> ArtifactManifest:
        """Whether the artifact can be built. Raises FactoryError if not."""

    @abstractmethod
    def select_base(self, package_path: Path, manifest: ArtifactManifest) -> BaseRef:
        """Pick the preset base image. Raises FactoryError if missing."""

    @abstractmethod
    async def execute(
        self,
        package_path: Path,
        base: BaseRef,
        options: dict[str, Any] | None = None,
        *,
        request_id: str,
        on_progress: Any | None = None,
    ) -> BuildResult:
        """Inject, assemble, tag, and write the archive."""
