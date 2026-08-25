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
from app.services.local_users.backend import _chown_path, _user_skills_dir

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


@dataclass(frozen=True)
class _InstallRequest:
    """一次安装请求参数（skill 标识 + 重装语义），减少内部方法形参个数（G.FNM.03）。"""

    skill_id: str
    version: str | None
    force: bool


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

        req = _InstallRequest(skill_id=skill_id, version=version, force=force)

        if self._client is not None:
            return await self._do_install(self._client, base_url, skills_dir, req)

        async with httpx.AsyncClient(
            timeout=settings.SKILLHUB_REQUEST_TIMEOUT,
            follow_redirects=True,
        ) as client:
            return await self._do_install(client, base_url, skills_dir, req)

    # ── 内部流程 ──────────────────────────────────────────────────────

    async def _do_install(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        skills_dir: Path,
        req: _InstallRequest,
    ) -> InstallSkillResult:
        # 任何破坏性 fs 变更前先校验 skills_state.json（存在且可读、结构合法），
        # 避免「已装好目录但状态文件损坏 → 500」的半成品残留。
        _precheck_skills_state(skills_dir)

        info = await self._fetch_artifact_info(client, base_url, req.skill_id, req.version)

        _validate_skill_name(info.name)
        if info.plugin_type.lower() not in _SKILL_LIKE_TYPES:
            raise InvalidSkillPackageError(f"不支持的资产类型: {info.plugin_type}")
        if info.file_size > settings.SKILLHUB_MAX_FILE_SIZE:
            raise PackageTooLargeError(info.file_size, settings.SKILLHUB_MAX_FILE_SIZE)

        # 冲突检查前置到下载前，常见 409 不再白下载整个 zip
        target = skills_dir / info.name
        if target.exists() and not req.force:
            raise SkillExistsError(info.name)

        content = await self._download_zip(client, info.download_url)

        if hashlib.sha256(content).hexdigest() != info.checksum_sha256:
            raise ChecksumMismatchError()

        tmp_dir = self._extract_skill(content)
        try:
            root = _find_skill_root(tmp_dir)
            self._stage_and_swap(root, target)
        finally:
            shutil.rmtree(str(tmp_dir), ignore_errors=True)

        installed_at = self._update_skills_state(skills_dir, info.name, req.skill_id, base_url)
        # 后端进程可能以 root 运行：落盘的 skill 与 skills_state.json 属主须修正为 AGENTOS_SYS_UID/GID
        _chown_path(skills_dir)
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

        try:
            data = (resp.json() or {}).get("data") or {}
        except json.JSONDecodeError as exc:
            raise SkillhubUpstreamError(resp.status_code, "artifacts 响应不是合法 JSON") from exc
        missing = [k for k in ("name", "version", "download_url", "checksum_sha256") if not data.get(k)]
        if missing:
            raise SkillhubUpstreamError(resp.status_code, f"artifacts 响应缺少字段: {missing}")
        try:
            file_size = int(data.get("file_size") or 0)
        except (TypeError, ValueError) as exc:
            raise SkillhubUpstreamError(resp.status_code, "artifacts 响应 file_size 非法") from exc
        return ArtifactInfo(
            asset_id=skill_id,
            name=str(data["name"]),
            version=str(data["version"]),
            download_url=str(data["download_url"]),
            checksum_sha256=str(data["checksum_sha256"]).lower(),
            file_size=file_size,
            plugin_type=str(data.get("plugin_type") or ""),
        )

    @staticmethod
    async def _download_zip(client: httpx.AsyncClient, download_url: str) -> bytes:
        """流式下载原始 zip（预签名 URL，可能带重定向）。

        按实际下载字节数硬性封顶（F-4）：不信上游声明的 file_size，
        防声明与实际不符/解压炸弹。返回完整 bytes，供 sha256 校验。
        """
        max_size = settings.SKILLHUB_MAX_FILE_SIZE
        chunks: list[bytes] = []
        total = 0
        try:
            async with client.stream("GET", download_url) as resp:
                if resp.status_code >= 400:
                    raise SkillhubUpstreamError(resp.status_code, "下载 skill 包失败")
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > max_size:
                        raise PackageTooLargeError(total, max_size)
                    chunks.append(chunk)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as exc:
            raise SkillhubConnectionError(f"下载 skill 包失败: {exc}") from exc
        return b"".join(chunks)

    @staticmethod
    def _extract_skill(content: bytes) -> Path:
        """安全解压到临时目录并返回该目录；失败时清理临时目录后抛异常。

        调用方负责在 finally 中 ``shutil.rmtree`` 删除返回值目录。
        按跨成员累计的实际解压字节数封顶（F-4：解压炸弹防护）。
        """
        max_size = settings.SKILLHUB_MAX_FILE_SIZE
        tmp_dir = Path(tempfile.mkdtemp(prefix="skillhub_"))
        try:
            extracted = 0
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for member in zf.infolist():
                    dest = _resolve_member_dest(tmp_dir, member)
                    if member.is_dir():
                        dest.mkdir(parents=True, exist_ok=True)
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, dest.open("wb") as out:
                        while True:
                            chunk = src.read(1024 * 64)
                            if not chunk:
                                break
                            extracted += len(chunk)
                            if extracted > max_size:
                                raise PackageTooLargeError(extracted, max_size)
                            out.write(chunk)
            _find_skill_root(tmp_dir)  # 校验结构合法（根或根下唯一子目录含 SKILL.md）
        except Exception:
            shutil.rmtree(str(tmp_dir), ignore_errors=True)
            raise
        return tmp_dir

    @staticmethod
    def _stage_and_swap(root: Path, target: Path) -> None:
        """F-1: 在目标同文件系统暂存完整内容后再原子替换。

        先把新内容完整写到 ``skills_dir`` 下的临时目录（同文件系统），
        成功后再删旧目录并 ``os.rename`` 原子替换——中途失败（磁盘满等）
        时旧版本仍在，且不留半成品目录。失败时清理暂存目录后抛异常。
        """
        staging = Path(
            tempfile.mkdtemp(prefix=f".install-tmp-{target.name}-", dir=str(target.parent))
        )
        try:
            shutil.copytree(str(root), str(staging), dirs_exist_ok=True)
            if target.exists():
                shutil.rmtree(str(target))
            os.rename(str(staging), str(target))
        except Exception:
            shutil.rmtree(str(staging), ignore_errors=True)
            raise

    @staticmethod
    def _update_skills_state(skills_dir: Path, name: str, skill_id: str, base_url: str) -> str:
        """在 local_skills[] 中按 name upsert 一条，返回 installed_at（UTC ISO）。"""
        state_path = skills_dir / "skills_state.json"
        state = _read_skills_state(state_path) or dict(_DEFAULT_STATE_SKELETON)

        installed_at = datetime.now(timezone.utc).isoformat()
        entry = {
            "name": name,
            "origin": f"{base_url}/api/v1/artifacts/{skill_id}",
            "source": "skillhub",
            "installed_at": installed_at,
        }
        state["local_skills"] = [e for e in state["local_skills"] if e.get("name") != name] + [entry]

        tmp = state_path.with_suffix(state_path.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(str(tmp), str(state_path))
            # 后端进程可能以 root 运行：写出的 skills_state.json 属主须修正为 AGENTOS_SYS_UID/GID
            _chown_path(state_path)
        except (OSError, TypeError) as exc:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise SkillhubStateError(f"skills_state.json 写入失败: {exc}") from exc
        return installed_at


# ── 工具函数 ──────────────────────────────────────────────────────────


def _resolve_member_dest(extract_root: Path, member: zipfile.ZipInfo) -> Path:
    """zip-slip 防护：拒绝绝对路径、Windows 盘符、``..`` 跳级、空段、越界成员。"""
    raw = member.filename
    name = raw.replace("\\", "/")
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in name.split("/"):
        raise InvalidSkillPackageError(f"skill 包包含非法路径: {raw}")
    parts = [p for p in name.split("/") if p]
    if not parts or any(p in (".", "..") for p in parts):
        raise InvalidSkillPackageError(f"skill 包包含非法路径: {raw}")
    dest = extract_root.joinpath(*parts)
    if not dest.resolve().is_relative_to(extract_root.resolve()):
        raise InvalidSkillPackageError(f"skill 包包含非法路径: {raw}")
    return dest


def _read_skills_state(state_path: Path) -> dict | None:
    """非破坏性读取并校验 skills_state.json；文件不存在返回 None，损坏抛 SkillhubStateError。"""
    if not state_path.is_file():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillhubStateError(f"skills_state.json 读取失败: {exc}") from exc
    if not isinstance(state, dict):
        raise SkillhubStateError("skills_state.json 顶层必须是 JSON 对象")
    local_skills = state.get("local_skills")
    if not isinstance(local_skills, list):
        raise SkillhubStateError("skills_state.json 的 local_skills 字段必须是数组")
    return state


def _precheck_skills_state(skills_dir: Path) -> None:
    """F-3: 任何破坏性 fs 变更前校验 skills_state.json（存在即可读且结构合法）；缺失则放行（骨架后建）。"""
    _read_skills_state(skills_dir / "skills_state.json")


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
