"""API 集成测试 — POST /api/v1/skills/install。

复用 conftest 的 client（内存 SQLite + 完整 app）+ admin_tokens fixture。
service 层用 monkeypatch 替换 ``skills_api.svc.install``，不触网。
"""

from unittest.mock import AsyncMock

import pytest

from app.api.v1 import skills as skills_api
from app.services.skillhub_service import (
    ChecksumMismatchError,
    InstallSkillResult,
    InvalidSkillPackageError,
    PackageTooLargeError,
    SkillExistsError,
    SkillNotFoundError,
    SkillhubConnectionError,
    SkillhubNotConfiguredError,
    SkillhubStateError,
    SkillhubUpstreamError,
)

# 合法 asset_id：32 位小写 hex（SkillHub 接口参考 GET /plugins items[].asset_id）
VALID_SKILL_ID = "482becff9f044ba9bad9caef2e43b539"


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
        monkeypatch.setattr(skills_api.svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": VALID_SKILL_ID, "version": "1.0.0", "force": False},
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
            username="admin", skill_id=VALID_SKILL_ID, version="1.0.0", force=False,
        )

    @staticmethod
    async def test_defaults_force_true(client, admin_tokens, monkeypatch):
        result = InstallSkillResult(name="s", version="1.0.0", install_path="/tmp/x", installed_at="t")
        mock_install = AsyncMock(return_value=result)
        monkeypatch.setattr(skills_api.svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": VALID_SKILL_ID},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 200
        mock_install.assert_awaited_once_with(
            username="admin", skill_id=VALID_SKILL_ID, version=None, force=True,
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
        monkeypatch.setattr(skills_api.svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": VALID_SKILL_ID, "force": False},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 409
        assert resp.json()["detail"] == "skill 已存在，如需覆盖请使用 force=true"

    @staticmethod
    async def test_503_not_configured(client, admin_tokens, monkeypatch):
        mock_install = AsyncMock(side_effect=SkillhubNotConfiguredError())
        monkeypatch.setattr(skills_api.svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": VALID_SKILL_ID},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 503
        assert "SKILLHUB_BASE_URL" in resp.json()["detail"]

    @staticmethod
    async def test_400_checksum_mapped(client, admin_tokens, monkeypatch):
        mock_install = AsyncMock(side_effect=ChecksumMismatchError())
        monkeypatch.setattr(skills_api.svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": VALID_SKILL_ID},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "skill 包校验和不匹配"

    @staticmethod
    async def test_404_not_found_mapped(client, admin_tokens, monkeypatch):
        mock_install = AsyncMock(side_effect=SkillNotFoundError())
        monkeypatch.setattr(skills_api.svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": VALID_SKILL_ID},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "skill 不存在或不可下载"

    @staticmethod
    async def test_502_connection_mapped(client, admin_tokens, monkeypatch):
        mock_install = AsyncMock(side_effect=SkillhubConnectionError("连接 SkillHub 失败: boom"))
        monkeypatch.setattr(skills_api.svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": VALID_SKILL_ID},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 502
        assert "boom" in resp.json()["detail"]

    @staticmethod
    async def test_404_upstream_404_mapped(client, admin_tokens, monkeypatch):
        # zip 下载路径：预签名链接失效/过期 → 上游 404 → 透传 404（spec 016）
        mock_install = AsyncMock(side_effect=SkillhubUpstreamError(404, "下载 skill 包失败"))
        monkeypatch.setattr(skills_api.svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": VALID_SKILL_ID},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert isinstance(detail, str)
        assert "下载 skill 包失败" in detail

    @staticmethod
    async def test_502_upstream_non_404_mapped(client, admin_tokens, monkeypatch):
        mock_install = AsyncMock(side_effect=SkillhubUpstreamError(500, "SkillHub 上游错误: HTTP 500"))
        monkeypatch.setattr(skills_api.svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": VALID_SKILL_ID},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 502
        detail = resp.json()["detail"]
        assert isinstance(detail, str)
        assert "HTTP 500" in detail

    @staticmethod
    async def test_400_package_too_large_mapped(client, admin_tokens, monkeypatch):
        mock_install = AsyncMock(side_effect=PackageTooLargeError(10**12, 10**9))
        monkeypatch.setattr(skills_api.svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": VALID_SKILL_ID},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 400
        assert "skill 包过大" in resp.json()["detail"]

    @staticmethod
    async def test_400_invalid_package_mapped(client, admin_tokens, monkeypatch):
        mock_install = AsyncMock(side_effect=InvalidSkillPackageError("skill 包缺少 SKILL.md，结构非法"))
        monkeypatch.setattr(skills_api.svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": VALID_SKILL_ID},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 400
        assert "SKILL.md" in resp.json()["detail"]

    @staticmethod
    async def test_500_state_error_mapped(client, admin_tokens, monkeypatch):
        mock_install = AsyncMock(side_effect=SkillhubStateError("skills_state.json 读取失败: boom"))
        monkeypatch.setattr(skills_api.svc, "install", mock_install)

        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": VALID_SKILL_ID},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 500
        assert "skills_state.json" in resp.json()["detail"]

    @staticmethod
    async def test_422_invalid_skill_id_pattern(client, admin_tokens, monkeypatch):
        # asset_id 必须 32 位小写 hex（schema pattern），非法 id 在进 service 前被 422 拦截
        resp = await client.post(
            "/api/v1/skills/install",
            json={"skill_id": "abc123"},
            headers=_auth(admin_tokens["access_token"]),
        )

        assert resp.status_code == 422
