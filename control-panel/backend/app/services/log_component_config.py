from dataclasses import dataclass
from typing import Optional

from app.config import settings


@dataclass
class ComponentConfig:
    id: str
    category: str
    name: str
    path: str
    description: str = ""


DEFAULT_COMPONENTS: list[dict] = [
    {"id": "control_panel", "name": "管理面", "path": settings.LOG_DIR},
    {"id": "jiuwen", "name": "九问", "path": "/home/agentos/users/{username}/.jiuwenswarm"},
    {"id": "tongtu", "name": "通途", "path": "/home/agentos/.jiuwenswarm/agent/.logs"},
    {"id": "yuanrong", "name": "元戎", "path": "/tmp/yr_sessions/latest/log"},
    {"id": "shaxiang", "name": "沙箱", "path": "/home/agentos/supervisor"},
]

_cached_components: Optional[list[ComponentConfig]] = None


def _build_components() -> list[ComponentConfig]:
    components: list[ComponentConfig] = []
    seen_ids: set[str] = set()

    for item in DEFAULT_COMPONENTS:
        cid = str(item.get("id", "")).strip()
        name = str(item.get("name", "")).strip()
        path = str(item.get("path", "")).strip()
        description = str(item.get("description", "")).strip()

        if not cid or not name or not path:
            continue
        if cid in seen_ids:
            continue
        seen_ids.add(cid)

        components.append(ComponentConfig(
            id=cid,
            category=cid,
            name=name,
            path=path,
            description=description,
        ))

    return components


def get_components(category: str | None = None) -> list[ComponentConfig]:
    global _cached_components
    if _cached_components is None:
        _cached_components = _build_components()
    if category:
        return [c for c in _cached_components if c.category == category]
    return list(_cached_components)


def get_component_by_id(component_id: str) -> ComponentConfig | None:
    for c in get_components():
        if c.id == component_id:
            return c
    return None


def get_category_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in get_components():
        counts[c.category] = counts.get(c.category, 0) + 1
    return counts


def get_categories() -> list[str]:
    seen: dict[str, bool] = {}
    for c in get_components():
        if c.category not in seen:
            seen[c.category] = True
    return list(seen.keys())
