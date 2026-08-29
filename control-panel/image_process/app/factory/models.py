"""Data objects used by the image factory (not persisted)."""

from __future__ import annotations

from dataclasses import dataclass, field


class FactoryError(Exception):
    """Raised when a package cannot be resolved or built."""


@dataclass(frozen=True)
class ArtifactManifest:
    name: str
    version: str
    display_name: str
    os: str
    arch: str
    libc: str


@dataclass(frozen=True)
class BaseRef:
    ref: str


@dataclass
class BuildResult:
    name: str
    version: str
    image_ref: str
    archive_path: str | None = None
    runtime_spec: dict = field(default_factory=dict)
    recipe_id: str = ""
    base_ref: str = ""
    image_digest: str = ""
    image_module_version: str = "1.0"
