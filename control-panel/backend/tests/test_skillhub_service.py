"""skillhub_service 单元测试 — 下载/校验/解压/状态维护。

用 httpx.MockTransport 伪造 SkillHub 与 MinIO 下载源，不触网。
settings 通过 monkeypatch 指向 tmp_path，避免污染真实 /home/agentos。
"""

import hashlib
import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from app.config import settings
from app.services.skillhub_service import (
    ChecksumMismatchError,
    InvalidSkillPackageError,
    PackageTooLargeError,
    SkillExistsError,
    SkillhubConnectionError,
    SkillhubNotConfiguredError,
    SkillhubStateError,
    SkillhubUpstreamError,
    SkillhubService,
    SkillNotFoundError,
)


# ── 测试构造工具 ──────────────────────────────────────────────────────


def _zip_bytes(entries: dict[str, str] | None = None) -> bytes:
    """构造 skill zip；默认含根目录 SKILL.md + scripts/run.sh。"""
    entries = entries or {
        "SKILL.md": "---\nname: my-demo-skill\n---\n# Demo",
        "scripts/run.sh": "echo hi",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _artifact_data(zip_data: bytes, **overrides) -> dict:
    data = {
        "download_url": "http://minio.test:3003/my-demo-skill.raw.zip",
        "version": "1.0.0",
        "checksum_sha256": hashlib.sha256(zip_data).hexdigest(),
        "name": "my-demo-skill",
        "file_size": len(zip_data),
        "asset_type": "plugin",
        "plugin_type": "skill",
    }
    data.update(overrides)
    return data


def _transport(
    zip_data: bytes | None = None,
    *,
    artifact_status: int = 200,
    artifact_data: dict | None = None,
    download_status: int = 200,
    connection_error: bool = False,
) -> httpx.MockTransport:
    """按请求 host 路由：skillhub.test → artifacts；minio.test → zip 下载。"""
    if connection_error:

        async def _raise_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("mock connection refused", request=request)

        return httpx.MockTransport(_raise_handler)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "skillhub.test":
            if artifact_status == 404:
                return httpx.Response(404, json={"code": 404, "message": "not found", "data": None})
            if artifact_status >= 400:
                return httpx.Response(
                    artifact_status, json={"code": artifact_status, "message": "error", "data": None}
                )
            data = artifact_data if artifact_data is not None else _artifact_data(zip_data or b"")
            return httpx.Response(200, json={"code": 200, "message": "Success", "data": data})
        if request.url.host == "minio.test":
            if download_status >= 400:
                return httpx.Response(download_status, json={"detail": "download failed"})
            return httpx.Response(200, content=zip_data or b"")
        return httpx.Response(404, json={"detail": "no route"})

    return httpx.MockTransport(handler)


def _configure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """把 settings 指向测试环境（SKILLHUB 可达 + tmp home）。"""
    monkeypatch.setattr(settings, "SKILLHUB_BASE_URL", "http://skillhub.test:8098")
    monkeypatch.setattr(settings, "SKILLHUB_REQUEST_TIMEOUT", 30.0)
    monkeypatch.setattr(settings, "SKILLHUB_MAX_FILE_SIZE", 10 * 1024 * 1024)
    monkeypatch.setattr(settings, "AGENTOS_HOME_BASE", str(tmp_path / "home"))
    monkeypatch.setattr(settings, "AGENTOS_USER_SKILLS_SUBDIR", ".jiuwenswarm/agent/workspace/skills")


def _skills_dir(tmp_path: Path) -> Path:
    return (
        Path(str(tmp_path)) / "home" / "alice" / ".jiuwenswarm/agent/workspace/skills"
    )


# ── 安装成功 / 参数转发 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_install_success(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(zip_data=_zip_bytes())))

    result = await svc.install("alice", "abc123")

    assert result.name == "my-demo-skill"
    assert result.version == "1.0.0"
    target = _skills_dir(tmp_path) / "my-demo-skill"
    assert result.install_path == str(target)
    assert (target / "SKILL.md").is_file()
    assert (target / "scripts" / "run.sh").is_file()
    assert result.installed_at.endswith("+00:00")


@pytest.mark.asyncio
async def test_install_chowns_skill_tree(tmp_path, monkeypatch):
    """安装后 skill 及 skills_state.json 应递归 chown 到 AGENTOS_SYS_UID/GID（修复属主残留为 root）。"""
    _configure(monkeypatch, tmp_path)
    calls: list[tuple[str, int, int]] = []

    def fake_chown(path, uid, gid, **kwargs):
        assert kwargs.get("follow_symlinks") is False
        calls.append((str(path), uid, gid))

    monkeypatch.setattr("os.chown", fake_chown)
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(zip_data=_zip_bytes())))

    await svc.install("alice", "abc123")

    skills_dir = _skills_dir(tmp_path)
    chowned = {p for p, _, _ in calls}
    assert chowned == {
        str(skills_dir),
        str(skills_dir / "skills_state.json"),
        str(skills_dir / "my-demo-skill"),
        str(skills_dir / "my-demo-skill" / "SKILL.md"),
        str(skills_dir / "my-demo-skill" / "scripts"),
        str(skills_dir / "my-demo-skill" / "scripts" / "run.sh"),
    }
    assert all((u, g) == (settings.AGENTOS_SYS_UID, settings.AGENTOS_SYS_GID) for _, u, g in calls)


@pytest.mark.asyncio
async def test_version_param_forwarded(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    seen: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "skillhub.test":
            seen["params"] = dict(request.url.params)
            return httpx.Response(200, json={"code": 200, "message": "Success", "data": _artifact_data(_zip_bytes())})
        return httpx.Response(200, content=_zip_bytes())

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    svc = SkillhubService(client=client)

    await svc.install("alice", "abc123", version="2.3.4")

    assert seen["params"] == {"is_cli_download": "false", "version": "2.3.4"}


# ── 上游错误 ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_not_configured_raises(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "SKILLHUB_BASE_URL", "")
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(zip_data=_zip_bytes())))

    with pytest.raises(SkillhubNotConfiguredError):
        await svc.install("alice", "abc123")


@pytest.mark.asyncio
async def test_artifact_not_found(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(artifact_status=404)))

    with pytest.raises(SkillNotFoundError):
        await svc.install("alice", "missing")


@pytest.mark.asyncio
async def test_upstream_500(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(artifact_status=500)))

    with pytest.raises(SkillhubUpstreamError) as exc:
        await svc.install("alice", "abc123")
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_connection_error(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(connection_error=True)))

    with pytest.raises(SkillhubConnectionError):
        await svc.install("alice", "abc123")


@pytest.mark.asyncio
async def test_download_http_error(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    svc = SkillhubService(
        client=httpx.AsyncClient(transport=_transport(zip_data=_zip_bytes(), download_status=500))
    )

    with pytest.raises(SkillhubUpstreamError):
        await svc.install("alice", "abc123")


# ── 校验失败 ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_checksum_mismatch(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    bad = _artifact_data(_zip_bytes(), checksum_sha256="0" * 64)
    svc = SkillhubService(
        client=httpx.AsyncClient(transport=_transport(zip_data=_zip_bytes(), artifact_data=bad))
    )

    with pytest.raises(ChecksumMismatchError):
        await svc.install("alice", "abc123")


@pytest.mark.asyncio
async def test_unsupported_plugin_type(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    data = _artifact_data(_zip_bytes(), plugin_type="agent-plugin")
    svc = SkillhubService(
        client=httpx.AsyncClient(transport=_transport(zip_data=_zip_bytes(), artifact_data=data))
    )

    with pytest.raises(InvalidSkillPackageError):
        await svc.install("alice", "abc123")


@pytest.mark.asyncio
async def test_package_too_large(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    data = _artifact_data(_zip_bytes(), file_size=10**12)
    svc = SkillhubService(
        client=httpx.AsyncClient(transport=_transport(zip_data=_zip_bytes(), artifact_data=data))
    )

    with pytest.raises(PackageTooLargeError):
        await svc.install("alice", "abc123")


@pytest.mark.asyncio
async def test_invalid_name_rejected(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    data = _artifact_data(_zip_bytes(), name="../escape")
    svc = SkillhubService(
        client=httpx.AsyncClient(transport=_transport(zip_data=_zip_bytes(), artifact_data=data))
    )

    with pytest.raises(InvalidSkillPackageError):
        await svc.install("alice", "abc123")


# ── force / 冲突 ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_force_false_existing_raises(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(zip_data=_zip_bytes())))
    await svc.install("alice", "abc123")

    with pytest.raises(SkillExistsError):
        await svc.install("alice", "abc123", force=False)


@pytest.mark.asyncio
async def test_force_true_overwrites(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(zip_data=_zip_bytes())))
    await svc.install("alice", "abc123")
    target = _skills_dir(tmp_path) / "my-demo-skill"
    (target / "stale.txt").write_text("stale", encoding="utf-8")

    await svc.install("alice", "abc123", force=True)

    assert not (target / "stale.txt").exists()
    assert (target / "SKILL.md").is_file()


# ── 解压安全 / 结构 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_zip_slip_rejected(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    evil = _zip_bytes({"../evil.txt": "boom", "SKILL.md": "---\nname: my-demo-skill\n---\n"})
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(zip_data=evil)))

    with pytest.raises(InvalidSkillPackageError):
        await svc.install("alice", "abc123")
    assert not (tmp_path / "evil.txt").exists()


@pytest.mark.asyncio
async def test_missing_skill_md(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    svc = SkillhubService(
        client=httpx.AsyncClient(transport=_transport(zip_data=_zip_bytes({"README.md": "no skill"})))
    )

    with pytest.raises(InvalidSkillPackageError):
        await svc.install("alice", "abc123")


@pytest.mark.asyncio
async def test_single_subdir_flattened(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    z = _zip_bytes({
        "my-demo-skill/SKILL.md": "---\nname: my-demo-skill\n---\n",
        "my-demo-skill/scripts/run.sh": "echo hi",
    })
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(zip_data=z)))

    result = await svc.install("alice", "abc123")

    target = Path(result.install_path)
    assert (target / "SKILL.md").is_file()
    assert (target / "scripts" / "run.sh").is_file()


# ── skills_state.json ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_state_created_with_skeleton(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(zip_data=_zip_bytes())))

    result = await svc.install("alice", "abc123")

    state_path = _skills_dir(tmp_path) / "skills_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert set(state) == {"marketplaces", "installed_plugins", "local_skills", "skill_configs"}
    assert state["installed_plugins"] == []
    assert state["local_skills"] == [{
        "name": "my-demo-skill",
        "origin": "http://skillhub.test:8098/api/v1/artifacts/abc123",
        "source": "skillhub",
        "installed_at": result.installed_at,
    }]


@pytest.mark.asyncio
async def test_state_upsert_on_reinstall(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(zip_data=_zip_bytes())))

    await svc.install("alice", "abc123")
    r2 = await svc.install("alice", "abc123", force=True)

    state = json.loads((_skills_dir(tmp_path) / "skills_state.json").read_text(encoding="utf-8"))
    assert len(state["local_skills"]) == 1
    assert state["local_skills"][0]["installed_at"] == r2.installed_at


@pytest.mark.asyncio
async def test_state_preserves_installed_plugins(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    skills_dir = _skills_dir(tmp_path)
    skills_dir.mkdir(parents=True)
    (skills_dir / "skills_state.json").write_text(json.dumps({
        "marketplaces": [],
        "installed_plugins": [{"name": "existing-plugin"}],
        "local_skills": [],
        "skill_configs": {},
    }), encoding="utf-8")
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(zip_data=_zip_bytes())))

    await svc.install("alice", "abc123")

    state = json.loads((skills_dir / "skills_state.json").read_text(encoding="utf-8"))
    assert state["installed_plugins"] == [{"name": "existing-plugin"}]
    assert [e["name"] for e in state["local_skills"]] == ["my-demo-skill"]


@pytest.mark.asyncio
async def test_state_corrupted_not_overwritten(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    skills_dir = _skills_dir(tmp_path)
    skills_dir.mkdir(parents=True)
    bad = "{ this is not json"
    (skills_dir / "skills_state.json").write_text(bad, encoding="utf-8")
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(zip_data=_zip_bytes())))

    with pytest.raises(SkillhubStateError):
        await svc.install("alice", "abc123")

    assert (skills_dir / "skills_state.json").read_text(encoding="utf-8") == bad
    # F-3：状态文件损坏在破坏性 fs 变更前即失败，目标目录不应被创建
    assert not (skills_dir / "my-demo-skill").exists()


@pytest.mark.asyncio
async def test_state_top_level_not_object_raises(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    skills_dir = _skills_dir(tmp_path)
    skills_dir.mkdir(parents=True)
    (skills_dir / "skills_state.json").write_text("[1, 2, 3]", encoding="utf-8")
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(zip_data=_zip_bytes())))

    with pytest.raises(SkillhubStateError):
        await svc.install("alice", "abc123")
    assert not (skills_dir / "my-demo-skill").exists()


@pytest.mark.asyncio
async def test_state_local_skills_not_list_raises(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    skills_dir = _skills_dir(tmp_path)
    skills_dir.mkdir(parents=True)
    bad = json.dumps({"marketplaces": [], "installed_plugins": [], "local_skills": "oops", "skill_configs": {}})
    (skills_dir / "skills_state.json").write_text(bad, encoding="utf-8")
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(zip_data=_zip_bytes())))

    with pytest.raises(SkillhubStateError):
        await svc.install("alice", "abc123")
    assert (skills_dir / "skills_state.json").read_text(encoding="utf-8") == bad


@pytest.mark.asyncio
async def test_no_state_tmp_left_after_write(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(zip_data=_zip_bytes())))

    await svc.install("alice", "abc123")

    state_path = _skills_dir(tmp_path) / "skills_state.json"
    assert state_path.is_file()
    assert not Path(str(state_path) + ".tmp").exists()


# ── zip-slip 变体（M2-7：嵌套跳级 / 反斜杠 / Windows 盘符） ─────────────


@pytest.mark.asyncio
async def test_zip_slip_nested_rejected(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    evil = _zip_bytes({"a/../evil.txt": "boom", "SKILL.md": "---\nname: my-demo-skill\n---\n"})
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(zip_data=evil)))

    with pytest.raises(InvalidSkillPackageError):
        await svc.install("alice", "abc123")
    assert not (tmp_path / "evil.txt").exists()


@pytest.mark.asyncio
async def test_zip_slip_backslash_rejected(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    evil = _zip_bytes({"..\\evil.txt": "boom", "SKILL.md": "---\nname: my-demo-skill\n---\n"})
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(zip_data=evil)))

    with pytest.raises(InvalidSkillPackageError):
        await svc.install("alice", "abc123")
    assert not (tmp_path / "evil.txt").exists()


@pytest.mark.asyncio
async def test_zip_slip_windows_drive_rejected(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    evil = _zip_bytes({"C:/evil.txt": "boom", "SKILL.md": "---\nname: my-demo-skill\n---\n"})
    svc = SkillhubService(client=httpx.AsyncClient(transport=_transport(zip_data=evil)))

    with pytest.raises(InvalidSkillPackageError):
        await svc.install("alice", "abc123")
    assert not (tmp_path / "evil.txt").exists()
