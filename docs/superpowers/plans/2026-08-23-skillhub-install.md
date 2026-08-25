# SkillHub 技能安装接口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在管理面后端实现 `POST /api/v1/skills/install`，从本地 SkillHub（`http://<host_ip>:8098`）下载公开 skill，校验后安装到当前登录用户的技能目录，并维护 `skills_state.json`。

**Architecture:** 新增独立领域服务 `SkillhubService`（可注入 httpx client 便于测试），按 spec 016 的 10 步流程执行：获取 artifacts 信息 → 类型/大小/名称校验 → 下载 zip → sha256 校验和 → 冲突检查（force）→ 安全解压（zip-slip 防护）→ 落盘 → 更新 `skills_state.json`（`local_skills` upsert）。路由层仿照 `thirdparty_agent.py` 用 `isinstance` 映射表把领域异常转成 HTTP 状态码；鉴权走 `require_permission(Resource.SKILLS, Action.WRITE)`，只装到 JWT 用户的本人目录。

**Tech Stack:** Python 3.11+ / FastAPI / httpx（AsyncClient + MockTransport 测试）/ pydantic-settings / pytest-asyncio（asyncio_mode=auto）。不触碰数据库。

## Global Constraints

- 只实现**后端安装接口**，不改 agentos-client、不改 SkillHub 市场侧。
- 只支持 SkillHub **公开 skill**（`GET /api/v1/artifacts/{id}` 匿名可访问）。
- **只安装到当前登录用户自己的目录**（从 JWT 取 `username`），请求体不接受 username；admin 视为普通用户，不做代装。
- 路径复用分支已有常量：`settings.AGENTOS_HOME_BASE` + `username` + `settings.AGENTOS_USER_SKILLS_SUBDIR`（经 `app.services.local_users.backend._user_skills_dir`），**禁止硬编码 `/home/agentos/users`**。
- skill 目录名来自 SkillHub 返回的资产 `name`，必须匹配 `^[a-z0-9][a-z0-9-]*$`（防路径注入）。
- 响应包装统一用 `app.schemas.litellm.ApiResponse`（`{code, message, data}`）。
- 错误响应体用 FastAPI 默认 `detail` **字符串**（spec 016 §错误码明确为 `{"detail": "..."}`；注意与 `thirdparty_agent.py` 的 `{"message": ...}` 对象刻意不同）。
- 部署配置：`deploy.sh --with-skillhub` 时写 `SKILLHUB_BASE_URL=http://<host_ip>:8098` 到 `control-panel/deploy/.env`；compose 注入 backend 容器。
- 测试约定：**后端 Python 测试在 WSL 运行**（项目约定）。工作目录 `control-panel/backend`，命令 `uv run pytest tests/<file> -v`。测试用内存 SQLite + MockTransport，不依赖真实 SkillHub/MinIO。
- 配置新增项默认值：`SKILLHUB_BASE_URL=""`（为空 → 503）、`SKILLHUB_REQUEST_TIMEOUT=30.0`、`SKILLHUB_MAX_FILE_SIZE=524_288_000`。
- 提交/PR 信息用中文（项目约定）；`.env.example` 不改动既有 immutable 默认值。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `control-panel/backend/app/config.py`（改） | 新增 3 个 SkillHub 配置项 |
| `control-panel/backend/.env.example`（改） | 追加 SkillHub 配置段 |
| `control-panel/deploy/.env.example`（改） | 追加 `SKILLHUB_BASE_URL` |
| `control-panel/backend/app/iam/permissions.py`（改） | 新增 `Resource.SKILLS`，user 角色授 read/write |
| `control-panel/backend/app/services/skillhub_service.py`（新） | `SkillhubService`：领域异常 + 10 步安装流程 + 工具函数 |
| `control-panel/backend/app/schemas/skillhub.py`（新） | `InstallSkillRequest` / `InstalledSkill` |
| `control-panel/backend/app/api/v1/skills.py`（新） | 路由 + 领域异常 → HTTP 映射 |
| `control-panel/backend/app/main.py`（改） | 注册 skills 路由 |
| `control-panel/backend/tests/test_skillhub_config.py`（新） | 配置默认值断言 |
| `control-panel/backend/tests/test_skillhub_permissions.py`（新） | 权限矩阵断言 |
| `control-panel/backend/tests/test_skillhub_service.py`（新） | service 单元测试（MockTransport） |
| `control-panel/backend/tests/test_skillhub_api.py`（新） | API 集成测试（401/403/200/409/503） |
| `control-panel/deploy/deploy.sh`（改） | `--with-skillhub` 块写入 `SKILLHUB_BASE_URL` |
| `control-panel/deploy/docker-compose.yml`（改） | backend env 注入 `SKILLHUB_*` |

依赖关系：Task 1（config/permissions）→ Task 2（service 用 config）→ Task 3（router 用 service + schemas）→ Task 4（deploy 注入，独立）。

---

### Task 1: 配置项 + IAM 权限矩阵

**Files:**
- Modify: `control-panel/backend/app/config.py`（在 `AGENTOS_USER_SKILLS_SUBDIR` 之后）
- Modify: `control-panel/backend/.env.example`（文件末尾追加）
- Modify: `control-panel/deploy/.env.example`（文件末尾追加）
- Modify: `control-panel/backend/app/iam/permissions.py`
- Test: `control-panel/backend/tests/test_skillhub_config.py`、`tests/test_skillhub_permissions.py`

**Interfaces:**
- Consumes: 无（独立基础层）。
- Produces: `settings.SKILLHUB_BASE_URL: str`、`settings.SKILLHUB_REQUEST_TIMEOUT: float`、`settings.SKILLHUB_MAX_FILE_SIZE: int`；`Resource.SKILLS == "skills"`；user 角色对 `Resource.SKILLS` 有 `{READ, WRITE}`。Task 2/3 依赖这些名字。

- [ ] **Step 1: 写失败的配置测试**

创建 `control-panel/backend/tests/test_skillhub_config.py`：

```python
"""配置项默认值断言 — SkillHub 市场。"""

from app.config import settings


def test_skillhub_settings_defaults():
    assert settings.SKILLHUB_BASE_URL == ""
    assert settings.SKILLHUB_REQUEST_TIMEOUT == 30.0
    assert settings.SKILLHUB_MAX_FILE_SIZE == 524_288_000
```

- [ ] **Step 2: 运行测试确认失败**

在 WSL 中：

```bash
cd /mnt/d/lab/agent-os/control-panel/backend && uv run pytest tests/test_skillhub_config.py -v
```

Expected: `FAILED` — `AttributeError: 'Settings' object has no attribute 'SKILLHUB_BASE_URL'`。

- [ ] **Step 3: 写失败的权限测试**

创建 `control-panel/backend/tests/test_skillhub_permissions.py`：

```python
"""权限矩阵 — Resource.SKILLS。"""

from app.iam.permissions import Action, PermissionService, Resource


def test_user_can_read_and_write_skills():
    assert PermissionService.check("user", Resource.SKILLS, Action.READ)
    assert PermissionService.check("user", Resource.SKILLS, Action.WRITE)


def test_admin_wildcard_grants_skills():
    assert PermissionService.check("admin", Resource.SKILLS, Action.WRITE)


def test_unknown_role_lacks_skills():
    assert not PermissionService.check("viewer", Resource.SKILLS, Action.WRITE)
```

- [ ] **Step 4: 运行权限测试确认失败**

```bash
cd /mnt/d/lab/agent-os/control-panel/backend && uv run pytest tests/test_skillhub_permissions.py -v
```

Expected: `FAILED` — `PermissionService.check("user", "skills", "write")` 返回 `False`。

- [ ] **Step 5: 实现配置项**

修改 `control-panel/backend/app/config.py`，在 `AGENTOS_USER_SKILLS_SUBDIR`（第 46 行）之后追加：

```python

    # ── SkillHub 市场 ──
    SKILLHUB_BASE_URL: str = ""  # 本地 SkillHub 前端地址，如 http://192.168.1.10:8098；为空时安装接口返回 503
    SKILLHUB_REQUEST_TIMEOUT: float = 30.0
    SKILLHUB_MAX_FILE_SIZE: int = 524_288_000  # 500 MB，与 thirdparty_agent 的 THIRDPARTY_AGENT_INSTALLER_MAX_BYTES 一致
```

在 `control-panel/backend/.env.example` 末尾追加：

```
# ── SkillHub 市场 ──
# 一体机本地 SkillHub 前端地址（如 http://192.168.1.10:8098）；为空时安装接口返回 503
# --with-skillhub 部署时由 deploy.sh 自动写入管理面 .env，此处保持默认
SKILLHUB_BASE_URL=
SKILLHUB_REQUEST_TIMEOUT=30.0
# 单个 skill 包大小上限（字节，默认 500MB）
SKILLHUB_MAX_FILE_SIZE=524288000
```

在 `control-panel/deploy/.env.example` 末尾追加：

```
# ── SkillHub 市场 ──
# 管理面 backend 下载 skill 用的 SkillHub 前端地址（--with-skillhub 时 deploy.sh 自动写入）
# 例如 http://192.168.1.10:8098；留空则安装接口返回 503
SKILLHUB_BASE_URL=
```

- [ ] **Step 6: 实现权限矩阵**

修改 `control-panel/backend/app/iam/permissions.py`：

1. 在 `Resource` 类末尾（`SETTINGS = "settings"` 之后）追加：

```python
    SKILLS = "skills"
```

2. 在 `_ALL_RESOURCES` 列表追加 `Resource.SKILLS,`（放在 `Resource.SETTINGS,` 之后）。

3. 在 `"user"` 角色字典追加 `Resource.SKILLS: {Action.READ, Action.WRITE},`（放在 `Resource.ALERTS` 之后）。

修改后相关片段：

```python
class Resource:
    ...
    SETTINGS = "settings"
    SKILLS = "skills"


_ROLE_PERMISSIONS: dict[str, dict[str, set[str]]] = {
    "admin": {
        "*": {"*"},
    },
    "user": {
        Resource.DASHBOARD: {Action.READ},
        Resource.INFERENCE_API_KEYS: {Action.READ, Action.WRITE},
        Resource.INFERENCE_USAGE: {Action.READ},
        Resource.APPS: {Action.READ},
        Resource.ALERTS: {Action.READ},
        Resource.SKILLS: {Action.READ, Action.WRITE},
    },
}

_ALL_RESOURCES = [
    ...
    Resource.SETTINGS,
    Resource.SKILLS,
]
```

- [ ] **Step 7: 运行测试确认通过**

```bash
cd /mnt/d/lab/agent-os/control-panel/backend && uv run pytest tests/test_skillhub_config.py tests/test_skillhub_permissions.py -v
```

Expected: `6 passed`（2 个配置 + 4 个权限断言）。

- [ ] **Step 8: 提交**

```bash
git add control-panel/backend/app/config.py control-panel/backend/app/iam/permissions.py \
        control-panel/backend/.env.example control-panel/deploy/.env.example \
        control-panel/backend/tests/test_skillhub_config.py control-panel/backend/tests/test_skillhub_permissions.py
git commit -m "feat: 新增 SkillHub 配置项与 skills 资源权限"
```

---

### Task 2: SkillhubService（下载/校验/解压/状态维护）

**Files:**
- Create: `control-panel/backend/app/services/skillhub_service.py`
- Test: `control-panel/backend/tests/test_skillhub_service.py`

**Interfaces:**
- Consumes: `settings.SKILLHUB_BASE_URL` / `SKILLHUB_REQUEST_TIMEOUT` / `SKILLHUB_MAX_FILE_SIZE`（Task 1）；`app.services.local_users.backend._user_skills_dir`。
- Produces:
  - 领域异常：`SkillhubError`（基类）、`SkillhubNotConfiguredError`、`SkillhubConnectionError`、`SkillhubUpstreamError(status_code)`、`SkillNotFoundError`、`SkillExistsError`、`ChecksumMismatchError`、`PackageTooLargeError`、`InvalidSkillPackageError`、`SkillhubStateError`。
  - `SkillhubService(client: httpx.AsyncClient | None = None)`，方法 `async install(username: str, skill_id: str, version: str | None = None, force: bool = True) -> InstallSkillResult`。
  - `InstallSkillResult(name, version, install_path, installed_at)`（frozen dataclass）。Task 3 路由消费这些名字。

- [ ] **Step 1: 写失败的 service 测试**

创建 `control-panel/backend/tests/test_skillhub_service.py`（完整文件）：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /mnt/d/lab/agent-os/control-panel/backend && uv run pytest tests/test_skillhub_service.py -v
```

Expected: 全部 `FAILED`，首个报 `ModuleNotFoundError: No module named 'app.services.skillhub_service'`。

- [ ] **Step 3: 实现 SkillhubService**

创建 `control-panel/backend/app/services/skillhub_service.py`（完整文件）：

```python
"""SkillhubService — 从 SkillHub 下载并安装 skill 到用户技能目录。

流程（spec 016 §安装流程）：
获取 artifacts 信息 → 名称/类型/大小校验 → 下载 zip → sha256 校验和 →
冲突检查（force）→ 安全解压（zip-slip 防护）→ 落盘 → 更新 skills_state.json。
"""

import hashlib
import io
import json
import logging
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.config import settings
from app.services.local_users.backend import _user_skills_dir

logger = logging.getLogger(__name__)

# 允许的 skill-like 资产类型（plugin_type，小写匹配）
_SKILL_LIKE_TYPES = {"skill", "swarmskill"}
# skill 目录名约束：小写字母/数字/连字符，防路径注入
_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

_DEFAULT_STATE_SKELETON: dict = {
    "marketplaces": [],
    "installed_plugins": [],
    "local_skills": [],
    "skill_configs": {},
}


# ── 领域异常 ──────────────────────────────────────────────────────────


class SkillhubError(Exception):
    """SkillHub 安装领域异常基类。"""


class SkillhubNotConfiguredError(SkillhubError):
    """SKILLHUB_BASE_URL 未配置。"""

    def __init__(self) -> None:
        super().__init__("SkillHub 未配置（SKILLHUB_BASE_URL 为空）")


class SkillhubConnectionError(SkillhubError):
    """连接 SkillHub / 下载源失败（连接、超时、DNS）。"""


class SkillhubUpstreamError(SkillhubError):
    """SkillHub 返回非 200 响应。"""

    def __init__(self, status_code: int, message: str = "") -> None:
        self.status_code = status_code
        super().__init__(message or f"SkillHub 上游错误: HTTP {status_code}")


class SkillNotFoundError(SkillhubError):
    """skill 不存在或不可下载。"""

    def __init__(self) -> None:
        super().__init__("skill 不存在或不可下载")


class SkillExistsError(SkillhubError):
    """同名 skill 已存在且 force=false。"""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__("skill 已存在，如需覆盖请使用 force=true")


class ChecksumMismatchError(SkillhubError):
    """下载包校验和不匹配。"""

    def __init__(self) -> None:
        super().__init__("skill 包校验和不匹配")


class PackageTooLargeError(SkillhubError):
    """包大小超过 SKILLHUB_MAX_FILE_SIZE。"""

    def __init__(self, size: int, max_size: int) -> None:
        self.size = size
        self.max_size = max_size
        super().__init__(f"skill 包过大: {size} 字节（上限 {max_size} 字节）")


class InvalidSkillPackageError(SkillhubError):
    """包结构非法：缺 SKILL.md / zip-slip / 类型不支持 / 名称非法。"""


class SkillhubStateError(SkillhubError):
    """skills_state.json 读取/更新失败（不静默覆盖用户数据）。"""


# ── 数据对象 ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ArtifactInfo:
    """SkillHub artifacts 接口返回的下载信息。"""

    asset_id: str
    name: str
    version: str
    download_url: str
    checksum_sha256: str
    file_size: int
    plugin_type: str


@dataclass(frozen=True)
class InstallSkillResult:
    """安装结果。"""

    name: str
    version: str
    install_path: str
    installed_at: str


class SkillhubService:
    """从 SkillHub 下载并安装 skill 到用户技能目录。"""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        """``client`` 用于测试注入 MockTransport 客户端；None 时每次调用自建。"""
        self._client = client

    # ── 公共入口 ──────────────────────────────────────────────────────

    async def install(
        self,
        username: str,
        skill_id: str,
        version: str | None = None,
        force: bool = True,
    ) -> InstallSkillResult:
        """下载并安装 skill 到 ``{AGENTOS_HOME_BASE}/{username}/<skills_subdir>``。

        ``username`` 来自 JWT（只装到本人目录），不接受外部传入。
        """
        base_url = settings.SKILLHUB_BASE_URL.strip().rstrip("/")
        if not base_url:
            raise SkillhubNotConfiguredError()

        skills_dir = _user_skills_dir(username)
        skills_dir.mkdir(parents=True, exist_ok=True)

        if self._client is not None:
            return await self._do_install(self._client, base_url, skills_dir, skill_id, version, force)

        async with httpx.AsyncClient(
            timeout=settings.SKILLHUB_REQUEST_TIMEOUT,
            follow_redirects=True,
        ) as client:
            return await self._do_install(client, base_url, skills_dir, skill_id, version, force)

    # ── 内部流程 ──────────────────────────────────────────────────────

    async def _do_install(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        skills_dir: Path,
        skill_id: str,
        version: str | None,
        force: bool,
    ) -> InstallSkillResult:
        info = await self._fetch_artifact_info(client, base_url, skill_id, version)

        _validate_skill_name(info.name)
        if info.plugin_type.lower() not in _SKILL_LIKE_TYPES:
            raise InvalidSkillPackageError(f"不支持的资产类型: {info.plugin_type}")
        if info.file_size > settings.SKILLHUB_MAX_FILE_SIZE:
            raise PackageTooLargeError(info.file_size, settings.SKILLHUB_MAX_FILE_SIZE)

        content = await self._download_zip(client, info.download_url)

        if hashlib.sha256(content).hexdigest() != info.checksum_sha256:
            raise ChecksumMismatchError()

        target = skills_dir / info.name
        if target.exists() and not force:
            raise SkillExistsError(info.name)

        tmp_dir = self._extract_skill(content)
        try:
            root = _find_skill_root(tmp_dir)
            if target.exists():
                shutil.rmtree(str(target))
            shutil.copytree(str(root), str(target))
        finally:
            shutil.rmtree(str(tmp_dir), ignore_errors=True)

        installed_at = self._update_skills_state(skills_dir, info.name, skill_id, base_url)
        return InstallSkillResult(
            name=info.name,
            version=info.version,
            install_path=str(target),
            installed_at=installed_at,
        )

    async def _fetch_artifact_info(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        skill_id: str,
        version: str | None,
    ) -> ArtifactInfo:
        """GET {base}/api/v1/artifacts/{id}?is_cli_download=false[&version=...] → 下载信息。"""
        params: dict[str, str] = {"is_cli_download": "false"}
        if version:
            params["version"] = version
        url = f"{base_url}/api/v1/artifacts/{skill_id}"
        try:
            resp = await client.get(url, params=params)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as exc:
            raise SkillhubConnectionError(f"连接 SkillHub 失败: {exc}") from exc

        if resp.status_code == 404:
            raise SkillNotFoundError()
        if resp.status_code >= 400:
            raise SkillhubUpstreamError(resp.status_code, resp.text[:200])

        data = (resp.json() or {}).get("data") or {}
        missing = [k for k in ("name", "version", "download_url", "checksum_sha256") if not data.get(k)]
        if missing:
            raise SkillhubUpstreamError(resp.status_code, f"artifacts 响应缺少字段: {missing}")
        return ArtifactInfo(
            asset_id=skill_id,
            name=str(data["name"]),
            version=str(data["version"]),
            download_url=str(data["download_url"]),
            checksum_sha256=str(data["checksum_sha256"]).lower(),
            file_size=int(data.get("file_size") or 0),
            plugin_type=str(data.get("plugin_type") or ""),
        )

    @staticmethod
    async def _download_zip(client: httpx.AsyncClient, download_url: str) -> bytes:
        """下载原始 zip（预签名 URL，可能带重定向）。"""
        try:
            resp = await client.get(download_url)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as exc:
            raise SkillhubConnectionError(f"下载 skill 包失败: {exc}") from exc
        if resp.status_code >= 400:
            raise SkillhubUpstreamError(resp.status_code, "下载 skill 包失败")
        return resp.content

    @staticmethod
    def _extract_skill(content: bytes) -> Path:
        """安全解压到临时目录并返回该目录；失败时清理临时目录后抛异常。

        调用方负责在 finally 中 ``shutil.rmtree`` 删除返回值目录。
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix="skillhub_"))
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for member in zf.infolist():
                    dest = _resolve_member_dest(tmp_dir, member)
                    if member.is_dir():
                        dest.mkdir(parents=True, exist_ok=True)
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, dest.open("wb") as out:
                        shutil.copyfileobj(src, out)
            _find_skill_root(tmp_dir)  # 校验结构合法（根或根下唯一子目录含 SKILL.md）
        except Exception:
            shutil.rmtree(str(tmp_dir), ignore_errors=True)
            raise
        return tmp_dir

    @staticmethod
    def _update_skills_state(skills_dir: Path, name: str, skill_id: str, base_url: str) -> str:
        """在 local_skills[] 中按 name upsert 一条，返回 installed_at（UTC ISO）。"""
        state_path = skills_dir / "skills_state.json"
        if state_path.is_file():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise SkillhubStateError(f"skills_state.json 读取失败: {exc}") from exc
        else:
            state = dict(_DEFAULT_STATE_SKELETON)

        if not isinstance(state, dict):
            raise SkillhubStateError("skills_state.json 顶层必须是 JSON 对象")
        local_skills = state.get("local_skills")
        if not isinstance(local_skills, list):
            raise SkillhubStateError("skills_state.json 的 local_skills 字段必须是数组")

        installed_at = datetime.now(timezone.utc).isoformat()
        entry = {
            "name": name,
            "origin": f"{base_url}/api/v1/artifacts/{skill_id}",
            "source": "skillhub",
            "installed_at": installed_at,
        }
        state["local_skills"] = [e for e in local_skills if e.get("name") != name] + [entry]

        tmp = state_path.with_suffix(state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(state_path))
        return installed_at


# ── 工具函数 ──────────────────────────────────────────────────────────


def _resolve_member_dest(extract_root: Path, member: zipfile.ZipInfo) -> Path:
    """zip-slip 防护：拒绝绝对路径、``..`` 跳级、空段、越界成员。"""
    raw = member.filename
    name = raw.replace("\\", "/")
    if name.startswith("/") or ".." in name.split("/"):
        raise InvalidSkillPackageError(f"skill 包包含非法路径: {raw}")
    parts = [p for p in name.split("/") if p]
    if not parts or any(p in (".", "..") for p in parts):
        raise InvalidSkillPackageError(f"skill 包包含非法路径: {raw}")
    dest = extract_root.joinpath(*parts)
    if not dest.resolve().is_relative_to(extract_root.resolve()):
        raise InvalidSkillPackageError(f"skill 包包含非法路径: {raw}")
    return dest


def _find_skill_root(extract_dir: Path) -> Path:
    """返回包含 SKILL.md 的 skill 根目录（根目录，或根下唯一子目录自动打平）。"""
    if (extract_dir / "SKILL.md").is_file():
        return extract_dir
    subdirs = [d for d in extract_dir.iterdir() if d.is_dir()]
    if len(subdirs) == 1 and (subdirs[0] / "SKILL.md").is_file():
        return subdirs[0]
    raise InvalidSkillPackageError("skill 包缺少 SKILL.md，结构非法")


def _validate_skill_name(name: str) -> None:
    """校验 skill 目录名（小写字母/数字/连字符），防路径注入。"""
    if not _SKILL_NAME_RE.match(name):
        raise InvalidSkillPackageError(f"非法 skill 名称: {name!r}")
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /mnt/d/lab/agent-os/control-panel/backend && uv run pytest tests/test_skillhub_service.py -v
```

Expected: `20 passed`。若有失败，先读断言再定位（多数失败会是 `_find_skill_root` 打平或 state 原子写细节）。

- [ ] **Step 5: 提交**

```bash
git add control-panel/backend/app/services/skillhub_service.py control-panel/backend/tests/test_skillhub_service.py
git commit -m "feat: 新增 SkillhubService 实现 skill 下载安装全流程"
```

---

### Task 3: Schemas + 路由 + main.py 注册 + API 测试

**Files:**
- Create: `control-panel/backend/app/schemas/skillhub.py`
- Create: `control-panel/backend/app/api/v1/skills.py`
- Modify: `control-panel/backend/app/main.py`
- Test: `control-panel/backend/tests/test_skillhub_api.py`

**Interfaces:**
- Consumes: `SkillhubService` + 各领域异常 + `InstallSkillResult`（Task 2）；`Resource.SKILLS` / `Action.WRITE`（Task 1）。
- Produces: 路由 `POST /api/v1/skills/install`（body `{skill_id, version?, force?}`，响应 `ApiResponse[InstalledSkill]`，错误 detail 为字符串）。

- [ ] **Step 1: 创建 schemas**

创建 `control-panel/backend/app/schemas/skillhub.py`：

```python
"""Pydantic 请求/响应模型 — SkillHub skill 安装。"""

from pydantic import BaseModel, Field


class InstallSkillRequest(BaseModel):
    """安装 skill 请求体。"""

    skill_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="SkillHub 公开 skill 的 asset_id（来自 GET /plugins 的 items[].asset_id）",
    )
    version: str | None = Field(None, description="版本号（x.y.z）；缺省安装最新公开版本")
    force: bool = Field(True, description="同名已存在时是否覆盖重装；false 则返回 409")


class InstalledSkill(BaseModel):
    """安装结果。"""

    name: str
    version: str
    install_path: str
    installed_at: str
```

- [ ] **Step 2: 写失败的 API 测试**

创建 `control-panel/backend/tests/test_skillhub_api.py`（完整文件）：

```python
"""API 集成测试 — POST /api/v1/skills/install。

复用 conftest 的 client（内存 SQLite + 完整 app）+ admin_tokens fixture。
service 层用 monkeypatch 替换 ``skills_api._svc.install``，不触网。
"""

from unittest.mock import AsyncMock

import pytest

from app.api.v1 import skills as skills_api
from app.services.skillhub_service import (
    ChecksumMismatchError,
    InstallSkillResult,
    SkillExistsError,
    SkillNotFoundError,
    SkillhubConnectionError,
    SkillhubNotConfiguredError,
)

_HEADERS = None  # 每个测试内注入 admin token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
class TestInstallSkill:
    @staticmethod
    async def test_requires_auth(client):
        resp = await client.post("/api/v1/skills/install", json={"skill_id": "abc123"})
        assert resp.status_code == 401

    @staticmethod
    async def test_success(client, admin_tokens, monkeypatch):
        result = InstallSkillResult(
            name="my-demo-skill",
            version="1.0.0",
            install_path="/home/agentos/users/admin/.jiuwenswarm/agent/workspace/skills/my-demo-skill",
            installed_at="2026-08-23T08:00:00+00:00",
        )
        mock_install = AsyncMock(return_value=result)
        monkeypatch.setattr(skills_api._svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": "482becff9f044ba9bad9caef2e43b539", "version": "1.0.0", "force": False},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert body["data"] == {
            "name": "my-demo-skill",
            "version": "1.0.0",
            "install_path": "/home/agentos/users/admin/.jiuwenswarm/agent/workspace/skills/my-demo-skill",
            "installed_at": "2026-08-23T08:00:00+00:00",
        }
        mock_install.assert_awaited_once_with(
            username="admin", skill_id="482becff9f044ba9bad9caef2e43b539", version="1.0.0", force=False,
        )

    @staticmethod
    async def test_defaults_force_true(client, admin_tokens, monkeypatch):
        result = InstallSkillResult(name="s", version="1.0.0", install_path="/tmp/x", installed_at="t")
        mock_install = AsyncMock(return_value=result)
        monkeypatch.setattr(skills_api._svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": "abc123"},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 200
        mock_install.assert_awaited_once_with(
            username="admin", skill_id="abc123", version=None, force=True,
        )

    @staticmethod
    async def test_403_without_permission(client, admin_tokens, monkeypatch):
        monkeypatch.setattr(
            "app.iam.permissions.PermissionService.check",
            lambda role, resource, action: False,
        )

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": "abc123"},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 403

    @staticmethod
    async def test_409_mapped(client, admin_tokens, monkeypatch):
        mock_install = AsyncMock(side_effect=SkillExistsError("my-demo-skill"))
        monkeypatch.setattr(skills_api._svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": "abc123", "force": False},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 409
        assert resp.json()["detail"] == "skill 已存在，如需覆盖请使用 force=true"

    @staticmethod
    async def test_503_not_configured(client, admin_tokens, monkeypatch):
        mock_install = AsyncMock(side_effect=SkillhubNotConfiguredError())
        monkeypatch.setattr(skills_api._svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": "abc123"},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 503
        assert "SKILLHUB_BASE_URL" in resp.json()["detail"]

    @staticmethod
    async def test_400_checksum_mapped(client, admin_tokens, monkeypatch):
        mock_install = AsyncMock(side_effect=ChecksumMismatchError())
        monkeypatch.setattr(skills_api._svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": "abc123"},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "skill 包校验和不匹配"

    @staticmethod
    async def test_404_not_found_mapped(client, admin_tokens, monkeypatch):
        mock_install = AsyncMock(side_effect=SkillNotFoundError())
        monkeypatch.setattr(skills_api._svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": "missing"},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "skill 不存在或不可下载"

    @staticmethod
    async def test_502_connection_mapped(client, admin_tokens, monkeypatch):
        mock_install = AsyncMock(side_effect=SkillhubConnectionError("连接 SkillHub 失败: boom"))
        monkeypatch.setattr(skills_api._svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": "abc123"},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 502
        assert "boom" in resp.json()["detail"]
```

- [ ] **Step 3: 运行测试确认失败**

```bash
cd /mnt/d/lab/agent-os/control-panel/backend && uv run pytest tests/test_skillhub_api.py -v
```

Expected: `FAILED` — 首个报 `ModuleNotFoundError: No module named 'app.api.v1.skills'`；未注册路由时 401 用例会报 404。

- [ ] **Step 4: 实现路由并注册**

创建 `control-panel/backend/app/api/v1/skills.py`：

```python
"""SkillHub skill 安装 API 路由。

鉴权：登录用户（含 admin）均可调用，只安装到 JWT 用户本人目录。
领域异常 → HTTP 映射仿照 thirdparty_agent.py（isinstance 表）；
注意错误 detail 用字符串（spec 016 §错误码），与 thirdparty_agent 的 {"message": ...} 刻意不同。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.iam.deps import Action, Resource, require_permission
from app.iam.tokens import TokenData
from app.schemas.litellm import ApiResponse
from app.schemas.skillhub import InstallSkillRequest, InstalledSkill
from app.services.skillhub_service import (
    ChecksumMismatchError,
    InvalidSkillPackageError,
    PackageTooLargeError,
    SkillExistsError,
    SkillNotFoundError,
    SkillhubConnectionError,
    SkillhubError,
    SkillhubNotConfiguredError,
    SkillhubService,
    SkillhubUpstreamError,
)

logger = logging.getLogger(__name__)

_svc = SkillhubService()

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])

# ── 领域异常 → HTTP 状态码 ──────────────────────────────────────────────

_EXCEPTION_STATUS: list[tuple[type[SkillhubError], int]] = [
    (SkillhubNotConfiguredError, 503),  # SKILLHUB_BASE_URL 为空
    (SkillhubConnectionError, 502),     # 连接失败 / 超时
    (SkillhubUpstreamError, 502),       # 上游非 200（404 已在 service 层转 SkillNotFoundError）
    (SkillNotFoundError, 404),          # skill 不存在或不可下载
    (SkillExistsError, 409),            # 已存在且 force=false
    (ChecksumMismatchError, 400),       # 校验和不一致
    (InvalidSkillPackageError, 400),    # 缺 SKILL.md / zip-slip / 类型不支持
    (PackageTooLargeError, 400),        # 超 SKILLHUB_MAX_FILE_SIZE
]


def _to_http(exc: SkillhubError) -> HTTPException:
    """Convert domain exception to HTTPException via isinstance mapping."""
    status = 500
    for cls, code in _EXCEPTION_STATUS:
        if isinstance(exc, cls):
            status = code
            break
    return HTTPException(status_code=status, detail=str(exc))


# ── Routes ──────────────────────────────────────────────────────────────


@router.post("/install", response_model=ApiResponse[InstalledSkill])
async def install_skill(
    body: InstallSkillRequest,
    user: TokenData = Depends(require_permission(Resource.SKILLS, Action.WRITE)),
) -> ApiResponse[InstalledSkill]:
    """从 SkillHub 下载并安装公开 skill 到当前用户技能目录。"""
    try:
        result = await _svc.install(
            username=user.username,
            skill_id=body.skill_id,
            version=body.version,
            force=body.force,
        )
    except SkillhubError as exc:
        logger.warning("skill install failed: %s", exc)
        raise _to_http(exc) from exc
    return ApiResponse(
        data=InstalledSkill(
            name=result.name,
            version=result.version,
            install_path=result.install_path,
            installed_at=result.installed_at,
        )
    )
```

修改 `control-panel/backend/app/main.py`：

1. 在 import 区（第 9 行 `from app.api.v1.thirdparty_agent import router ...` 之后）追加：

```python
from app.api.v1.skills import router as skills_router
```

2. 在 `app.include_router(thirdparty_agent_router)`（第 275 行）之后追加：

```python
app.include_router(skills_router)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd /mnt/d/lab/agent-os/control-panel/backend && uv run pytest tests/test_skillhub_api.py -v
```

Expected: `9 passed`。

- [ ] **Step 6: 回归——确认现有测试不受影响**

```bash
cd /mnt/d/lab/agent-os/control-panel/backend && uv run pytest tests/test_main.py tests/test_auth.py -v
```

Expected: 全部 `passed`（新增路由不应破坏现有套件）。

- [ ] **Step 7: 提交**

```bash
git add control-panel/backend/app/schemas/skillhub.py control-panel/backend/app/api/v1/skills.py \
        control-panel/backend/app/main.py control-panel/backend/tests/test_skillhub_api.py
git commit -m "feat: 新增 POST /api/v1/skills/install 路由并注册"
```

---

### Task 4: 部署接线（deploy.sh + docker-compose）

**Files:**
- Modify: `control-panel/deploy/deploy.sh`（`do_install` 的 `--with-skillhub` 块）
- Modify: `control-panel/deploy/docker-compose.yml`（backend env 块）

**Interfaces:**
- Consumes: `SKILLHUB_BASE_URL`（Task 1 已加到 deploy/.env.example）。
- Produces: `--with-skillhub` 部署时管理面 `.env` 注入 `SKILLHUB_BASE_URL=http://<host_ip>:8098`；compose 传给 backend 容器。

- [ ] **Step 1: 修改 deploy.sh**

`control-panel/deploy/deploy.sh` 的 `do_install` 中，在 `--with-skillhub` 块（`AGENTOS_PRESET_SKILLS_DIR` 写完之后、`fi` 之前，约第 1084 行后）追加：

```bash

        # 配置 SkillHub 访问地址（管理面 backend 下载 skill 用；与 skillhub.sh 的 host_ip 保持一致）
        local detected_ip skillhub_frontend_port skillhub_url
        detected_ip=$(detect_host_ip)
        skillhub_frontend_port="${SKILLHUB_FRONTEND_PORT:-8098}"
        skillhub_url="http://${detected_ip}:${skillhub_frontend_port}"
        if ! grep -q "^SKILLHUB_BASE_URL=" "$env_file" 2>/dev/null; then
            echo "SKILLHUB_BASE_URL=${skillhub_url}" >> "$env_file"
        else
            sed -i "s|^SKILLHUB_BASE_URL=.*|SKILLHUB_BASE_URL=${skillhub_url}|" "$env_file"
        fi
        log "  SKILLHUB_BASE_URL=${skillhub_url}"
```

插入后该块完整形态：

```bash
    # skillhub（仅 master + --with-skillhub）
    if is_master && [ "$WITH_SKILLHUB" -eq 1 ]; then
        log "[skillhub] install"
        AGENTOS_PORT="$(env_default FRONTEND_PORT 8090)" bash "${DEPLOY_DIR}/skillhub/skillhub.sh" install

        # 配置预装 skill 源目录（供 control-panel backend 创建用户时拷贝）
        local preset_dir="${DEPLOY_DIR}/skillhub/extracted-skills"
        mkdir -p "$preset_dir"
        local env_file="${DEPLOY_DIR}/.env"
        if ! grep -q "^AGENTOS_PRESET_SKILLS_DIR=" "$env_file" 2>/dev/null; then
            echo "AGENTOS_PRESET_SKILLS_DIR=${preset_dir}" >> "$env_file"
        else
            sed -i "s|^AGENTOS_PRESET_SKILLS_DIR=.*|AGENTOS_PRESET_SKILLS_DIR=${preset_dir}|" "$env_file"
        fi
        log "  AGENTOS_PRESET_SKILLS_DIR=${preset_dir}"

        # 配置 SkillHub 访问地址（管理面 backend 下载 skill 用；与 skillhub.sh 的 host_ip 保持一致）
        local detected_ip skillhub_frontend_port skillhub_url
        detected_ip=$(detect_host_ip)
        skillhub_frontend_port="${SKILLHUB_FRONTEND_PORT:-8098}"
        skillhub_url="http://${detected_ip}:${skillhub_frontend_port}"
        if ! grep -q "^SKILLHUB_BASE_URL=" "$env_file" 2>/dev/null; then
            echo "SKILLHUB_BASE_URL=${skillhub_url}" >> "$env_file"
        else
            sed -i "s|^SKILLHUB_BASE_URL=.*|SKILLHUB_BASE_URL=${skillhub_url}|" "$env_file"
        fi
        log "  SKILLHUB_BASE_URL=${skillhub_url}"
    fi
```

- [ ] **Step 2: 修改 docker-compose.yml**

`control-panel/deploy/docker-compose.yml` backend 服务 env 块，在 `AGENTOS_PRESET_SKILLS_DIR: ${AGENTOS_PRESET_SKILLS_DIR:-}`（第 58 行）之后追加：

```yaml
      # ── SkillHub 市场（--with-skillhub 时写入；为空则安装接口返回 503）──
      SKILLHUB_BASE_URL: ${SKILLHUB_BASE_URL}
      SKILLHUB_REQUEST_TIMEOUT: ${SKILLHUB_REQUEST_TIMEOUT:-30.0}
      SKILLHUB_MAX_FILE_SIZE: ${SKILLHUB_MAX_FILE_SIZE:-524288000}
```

- [ ] **Step 3: 语法校验**

```bash
cd /d/lab/agent-os/control-panel/deploy && bash -n deploy.sh && docker compose -f docker-compose.yml config >/dev/null && echo "config OK"
```

Expected: 输出 `config OK`（`bash -n` 无输出即语法通过）。

> 注：若本机无 docker compose，`docker compose ... config` 会失败——此时仅执行 `bash -n deploy.sh` 校验脚本语法，compose 校验可在有 docker 的一体机部署时验证。

- [ ] **Step 4: 提交**

```bash
git add control-panel/deploy/deploy.sh control-panel/deploy/docker-compose.yml
git commit -m "feat: skillhub 部署注入 SKILLHUB_BASE_URL"
```

---

## 验证总览（全部完成后）

```bash
# WSL，control-panel/backend
uv run pytest tests/test_skillhub_config.py tests/test_skillhub_permissions.py \
              tests/test_skillhub_service.py tests/test_skillhub_api.py -v
```

Expected: 全部通过（配置 1 + 权限 3 + service 20 + API 9 = 33 项）。

对照 spec 016 验收标准：
- 功能：安装落盘到 `{AGENTOS_HOME_BASE}/{username}/.jiuwenswarm/agent/workspace/skills/{name}` ✓；`local_skills` upsert 且 `installed_plugins` 不动 ✓；`force=true` 覆盖 / `false` 409 ✓；`version` 透传 ✓。
- 安全：401 / 403 ✓；zip-slip 拒绝 ✓；checksum 校验 ✓；只装本人目录 ✓（username 来自 JWT）。
- 部署：`--with-skillhub` 写 `SKILLHUB_BASE_URL` ✓；compose 注入 ✓。
