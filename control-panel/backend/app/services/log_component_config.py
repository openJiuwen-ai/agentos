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


_AGENT_LOG_DIR = "/home/agentos/host_root/.jiuwenswarm/agent/.logs"

DEFAULT_COMPONENTS: list[dict] = [
    {"id": "control_panel", "name": "管理面", "path": settings.LOG_DIR},
    {"id": "jiuwenswarm", "name": "jiuwenswarm", "path": "/home/agentos/users"},
    {"id": "agent-gateway", "name": "agent-gateway", "path": f"{_AGENT_LOG_DIR}/gateway.log"},
    {"id": "agent-registry", "name": "agent-registry", "path": f"{_AGENT_LOG_DIR}/registry.log"},
    {"id": "agent-runtime", "name": "agent-runtime", "path": "/tmp/yr_sessions/latest/logs"},
    {"id": "jiuwenbox", "name": "jiuwenbox", "path": "/tmp/jiuwenbox"},
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
