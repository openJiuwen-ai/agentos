"""VictoriaMetrics agent-metrics.json 同步 — 模型 instance_url / inference_engine 变更时更新。

job label 格式：``{inference_engine}-{host:port}``（inference_engine 统一小写）
其中 inference_engine 对应「部署框架」（如 vLLM → vllm）
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import settings

_file_lock = threading.Lock()


class AgentMetricsConfigError(Exception):
    """agent-metrics.json 读写或格式错误。"""


def get_config_path() -> Path:
    """返回 agent-metrics.json 的绝对路径。"""
    return Path(settings.AGENT_METRICS_CONFIG_PATH.strip())


def normalize_target(instance_url: str) -> str:
    """从 instance_url 提取 host:port（VictoriaMetrics targets 格式）。"""
    url = instance_url.strip()
    if not url:
        raise AgentMetricsConfigError("instance_url 不能为空")

    if "://" not in url:
        return url.rstrip("/")

    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise AgentMetricsConfigError(f"无效的 instance_url: {instance_url}")

    if parsed.port:
        return f"{host}:{parsed.port}"
    return host


def build_job(inference_engine: str, target: str) -> str:
    """job 唯一拼法：``{inference_engine}-{target}``，引擎名统一小写。"""
    engine = inference_engine.strip().lower()
    if not engine:
        raise AgentMetricsConfigError("inference_engine 不能为空")
    if not target.strip():
        raise AgentMetricsConfigError("target 不能为空")
    return f"{engine}-{target}"


def build_entry(inference_engine: str, instance_url: str) -> dict[str, Any]:
    target = normalize_target(instance_url)
    return {
        "targets": [target],
        "labels": {"job": build_job(inference_engine, target)},
    }


def _load_entries_unlocked(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return []
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise AgentMetricsConfigError(
            f"agent-metrics.json 格式错误: {path}"
        ) from e
    if not isinstance(data, list):
        raise AgentMetricsConfigError(
            f"agent-metrics.json 根节点必须是数组: {path}"
        )
    return data


def _save_entries_unlocked(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _find_index_by_job(
    entries: list[dict[str, Any]], job: str,
) -> int | None:
    for i, entry in enumerate(entries):
        labels = entry.get("labels") or {}
        if labels.get("job") == job:
            return i
    return None


def add_entry(inference_engine: str, instance_url: str) -> str:
    """追加一条 scrape target，返回 job label。已存在相同 job 时幂等返回。"""
    entry = build_entry(inference_engine, instance_url)
    job = entry["labels"]["job"]
    path = get_config_path()

    with _file_lock:
        entries = _load_entries_unlocked(path)
        if _find_index_by_job(entries, job) is not None:
            return job
        entries.append(entry)
        _save_entries_unlocked(path, entries)
    return job


def update_entry(
    old_job: str | None,
    inference_engine: str,
    instance_url: str,
) -> str:
    """更新已有条目（按 old_job 定位），返回新的 job label。"""
    new_entry = build_entry(inference_engine, instance_url)
    new_job = new_entry["labels"]["job"]
    path = get_config_path()

    with _file_lock:
        entries = _load_entries_unlocked(path)
        idx: int | None = None
        if old_job:
            idx = _find_index_by_job(entries, old_job)

        if idx is None:
            target = normalize_target(instance_url)
            for i, entry in enumerate(entries):
                targets = entry.get("targets") or []
                if target in targets:
                    idx = i
                    break

        if idx is not None:
            entries.pop(idx)

        existing_new = _find_index_by_job(entries, new_job)
        if existing_new is not None:
            entries.pop(existing_new)

        entries.append(new_entry)
        _save_entries_unlocked(path, entries)
    return new_job


def remove_entry(
    job: str | None,
    instance_url: str | None = None,
    inference_engine: str | None = None,
) -> bool:
    """删除条目，按 job 优先，否则按 target / 计算 job 匹配。返回是否删除。"""
    path = get_config_path()

    with _file_lock:
        entries = _load_entries_unlocked(path)
        idx: int | None = None

        if job:
            idx = _find_index_by_job(entries, job)

        if idx is None and instance_url and inference_engine:
            computed_job = build_job(
                inference_engine, normalize_target(instance_url),
            )
            idx = _find_index_by_job(entries, computed_job)

        if idx is None and instance_url:
            target = normalize_target(instance_url)
            for i, entry in enumerate(entries):
                targets = entry.get("targets") or []
                if target in targets:
                    idx = i
                    break

        if idx is None:
            return False

        entries.pop(idx)
        _save_entries_unlocked(path, entries)
        return True
