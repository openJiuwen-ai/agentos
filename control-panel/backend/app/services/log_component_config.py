import os
import re
from dataclasses import dataclass
from typing import Optional

from app.config import settings


@dataclass
class MergeRule:
    pattern: str
    name: str


@dataclass
class ComponentConfig:
    id: str
    category: str
    name: str
    path: str
    description: str = ""
    merge_rules: tuple[MergeRule, ...] = ()


_AGENT_LOG_DIR = "/var/log/agentos"

DEFAULT_COMPONENTS: list[dict] = [
    {"id": "control_panel", "name": "管理面", "path": settings.LOG_DIR},
    {"id": "jiuwenswarm", "name": "jiuwenswarm", "path": "/home/agentos/users"},
    {"id": "agent-gateway", "name": "agent-gateway", "path": f"{_AGENT_LOG_DIR}/gateway.log"},
    {"id": "agent-registry", "name": "agent-registry", "path": f"{_AGENT_LOG_DIR}/a2x-registry.log"},
    {"id": "agent-runtime", "name": "agent-runtime", "path": f"{_AGENT_LOG_DIR}/yr_sessions/latest/logs",
     "merge_rules": [
         {"pattern": r"^runtime-[^/]*[.](err|out)$", "name": "runtime-merged.log"},
     ]},
    {"id": "jiuwenbox", "name": "jiuwenbox", "path": "/tmp/jiuwenbox"},
    {"id": "agentos-node-service", "name": "推理服务节点", "path": f"{_AGENT_LOG_DIR}/agentos-node-service"},
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

        merge_rules = tuple(
            MergeRule(
                pattern=str(rule.get("pattern", "")).strip(),
                name=str(rule.get("name", "")).strip(),
            )
            for rule in item.get("merge_rules", [])
            if rule.get("pattern") and rule.get("name")
        )

        components.append(ComponentConfig(
            id=cid,
            category=cid,
            name=name,
            path=path,
            description=description,
            merge_rules=merge_rules,
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


def match_merge_rule(comp: ComponentConfig, relative_path: str) -> MergeRule | None:
    basename = os.path.basename(relative_path)
    for rule in comp.merge_rules:
        try:
            if re.fullmatch(rule.pattern, basename):
                return rule
        except re.error:
            continue
    return None


def merge_relative_paths(
    comp: ComponentConfig, relative_paths: list[str]
) -> list[str]:
    """把匹配合并规则的文件折叠为一个虚拟文件，其余保持原样。"""
    if not comp.merge_rules:
        return sorted(set(relative_paths))

    virtual: list[str] = []
    remaining: list[str] = []
    matched_names: set[str] = set()
    for p in relative_paths:
        rule = match_merge_rule(comp, p)
        if rule is None:
            remaining.append(p)
        elif rule.name not in matched_names:
            virtual.append(rule.name)
            matched_names.add(rule.name)
    return sorted(set(virtual + remaining))


def _logql_literal(s: str) -> str:
    """把字面量转成不含反斜杠的正则片段（LogQL 字符串内反斜杠转义会干扰解析）。"""
    escaped = re.escape(s)
    parts: list[str] = []
    i = 0
    while i < len(escaped):
        if escaped[i] == "\\" and i + 1 < len(escaped):
            parts.append(f"[{escaped[i + 1]}]")
            i += 2
        else:
            parts.append(escaped[i])
            i += 1
    return "".join(parts)


def build_merge_regex(comp: ComponentConfig, virtual_name: str) -> str | None:
    """虚拟文件名 -> 匹配全部被合并文件的 Loki filename 正则。"""
    for rule in comp.merge_rules:
        if rule.name == virtual_name:
            base = comp.path.rstrip("/")
            body = rule.pattern
            body = body[1:] if body.startswith("^") else body
            body = body[:-1] if body.endswith("$") else body
            return f"{_logql_literal(base)}/(?:.*/)?{body}"
    return None


def find_merge_virtual_name(filename_regex: str) -> str | None:
    """filename 正则是某个合并虚拟文件的展开时，返回其虚拟文件名。"""
    for comp in get_components():
        for rule in comp.merge_rules:
            if build_merge_regex(comp, rule.name) == filename_regex:
                return rule.name
    return None
