"""OAuth2 Provider 集成测试 + 核心单元测试。

使用 conftest.py 的 client + admin_tokens fixture（内存 SQLite + local_users backend）。
OAuth2 测试配置由 conftest 统一提供（环境变量在导入 app 前设置，
否则 app.main 模块级 _OAUTH2_ENABLED 不会注册 oauth2 路由）。
"""

import secrets
import uuid as uuid_mod
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

CLIENT_ID = "skillhub"
CLIENT_SECRET = "test-secret"
REDIRECT_URI = "http://localhost:9002/api/v1/auth/oauth/agentos/callback"


# ── Helpers ────────────────────────────────────────────────────────────


async def _admin_user_id() -> str:
    """获取本次测试中真实 admin 的 user_id（种子用户使用随机 uuid4）。"""
    from app.services import get_user_backend

    admin = await get_user_backend().get_user_by_username("admin")
    assert admin is not None, "种子 admin 用户不存在"
    return str(admin.user_id)


async def _insert_auth_code(user_id: str, *, created_at: datetime | None = None) -> str:
    """直接向数据库插入一条授权码，返回 code。"""
    import app.database as _db
    from app.models.oauth2_auth_code import OAuth2AuthorizationCode

    code = secrets.token_hex(32)
    async with _db.async_session_maker() as session:
        session.add(
            OAuth2AuthorizationCode(
                code=code,
                user_id=uuid_mod.UUID(user_id),
                client_id=CLIENT_ID,
                redirect_uri=REDIRECT_URI,
                created_at=created_at or datetime.utcnow(),
            )
        )
        await session.commit()
    return code


def _exchange_request(client, *, code: str, client_id: str = CLIENT_ID,
                      client_secret: str = CLIENT_SECRET, grant_type: str = "authorization_code"):
    """构造 POST /oauth2/token 请求（保持参数与生产一致的 form 编码）。"""
    return client.post(
        "/api/v1/oauth2/token",
        data={
            "grant_type": grant_type,
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )


# ── GET /oauth2/authorize ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_authorize_redirects_to_frontend(client):
    """有效的 client_id + redirect_uri → 302 重定向到前端。"""
    resp = await client.get(
        "/api/v1/oauth2/authorize",
        params={
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "state": "random-state",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("https://test/oauth/authorize?")
    # 零 Cookie 设计：OAuth 参数通过 URL query string 传递
    query = parse_qs(urlparse(location).query)
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == [REDIRECT_URI]
    assert query["state"] == ["random-state"]
    assert query["client_name"] == ["SkillHub"]
    assert "set-cookie" not in resp.headers


@pytest.mark.asyncio
async def test_authorize_missing_state_still_redirects(client):
    """state 为可选参数（CSRF 由客户端生成）→ 缺省时透传空字符串。"""
    resp = await client.get(
        "/api/v1/oauth2/authorize",
        params={"client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    query = parse_qs(urlparse(resp.headers["location"]).query, keep_blank_values=True)
    assert query["state"] == [""]


@pytest.mark.asyncio
async def test_authorize_invalid_client_id(client):
    """未知 client_id → 302 重定向到前端错误页。"""
    resp = await client.get(
        "/api/v1/oauth2/authorize",
        params={"client_id": "unknown", "redirect_uri": REDIRECT_URI},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/oauth/error" in resp.headers["location"]


@pytest.mark.asyncio
async def test_authorize_redirect_uri_mismatch(client):
    """redirect_uri 不匹配（防开放重定向）→ 302 重定向到前端错误页。"""
    resp = await client.get(
        "/api/v1/oauth2/authorize",
        params={"client_id": CLIENT_ID, "redirect_uri": "http://evil.com/callback"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/oauth/error" in resp.headers["location"]


# ── POST /oauth2/authorize（同意/拒绝决策） ─────────────────────────────


@pytest.fixture
def sqlite_uuid_compat(monkeypatch):
    """SQLite 测试库兼容垫片：将 str user_id 收敛为 uuid.UUID（仅测试环境，不改生产代码）。"""
    from app.models import oauth2_auth_code as mod

    original_create = mod.OAuth2AuthorizationCode.create.__func__

    @classmethod
    async def _create(cls, session, *, user_id, client_id, redirect_uri):
        uid = user_id if isinstance(user_id, uuid_mod.UUID) else uuid_mod.UUID(user_id)
        return await original_create(
            cls, session, user_id=uid, client_id=client_id, redirect_uri=redirect_uri
        )

    monkeypatch.setattr(mod.OAuth2AuthorizationCode, "create", _create)


@pytest.mark.asyncio
async def test_authorize_decision_allow_issues_usable_code(
    client, admin_tokens, sqlite_uuid_compat
):
    """allow → 返回含 code 的 redirect_uri，且 code 可端到端换取 access_token。"""
    resp = await client.post(
        "/api/v1/oauth2/authorize",
        json={
            "action": "allow",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "state": "st-123",
        },
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert resp.status_code == 200
    redirect = resp.json()["redirect_uri"]
    assert redirect.startswith(REDIRECT_URI + "?")
    query = parse_qs(urlparse(redirect).query)
    assert query["state"] == ["st-123"]
    code = query["code"][0]
    assert len(code) == 64  # secrets.token_hex(32) → 256 位随机

    # 端到端：签发的授权码可直接在 token endpoint 兑换
    token_resp = await _exchange_request(client, code=code)
    assert token_resp.status_code == 200
    assert token_resp.json()["access_token"]


@pytest.mark.asyncio
async def test_authorize_decision_deny(client, admin_tokens):
    """deny → 返回 error=access_denied 的 redirect_uri，不签发授权码。"""
    resp = await client.post(
        "/api/v1/oauth2/authorize",
        json={
            "action": "deny",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "state": "st-deny",
        },
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert resp.status_code == 200
    query = parse_qs(urlparse(resp.json()["redirect_uri"]).query)
    assert query["error"] == ["access_denied"]
    assert query["state"] == ["st-deny"]
    assert "code" not in query


@pytest.mark.asyncio
async def test_authorize_decision_invalid_action(client, admin_tokens):
    """action 既非 allow 也非 deny → 400。"""
    resp = await client.post(
        "/api/v1/oauth2/authorize",
        json={
            "action": "maybe",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "state": "",
        },
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client_id", "redirect_uri", "expected_error"),
    [
        ("evil", REDIRECT_URI, "Unknown client"),
        (CLIENT_ID, "http://evil.com/callback", "Invalid redirect_uri"),
    ],
)
async def test_authorize_decision_tampered_params(
    client, admin_tokens, client_id, redirect_uri, expected_error
):
    """前端回传的 OAuth 参数被篡改 → 400（服务端二次校验）。"""
    resp = await client.post(
        "/api/v1/oauth2/authorize",
        json={
            "action": "allow",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": "",
        },
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == expected_error


@pytest.mark.asyncio
async def test_authorize_decision_requires_cp_login(client):
    """决策端点身份来源是 CP 登录 JWT → 未携带 Bearer → 401。"""
    resp = await client.post(
        "/api/v1/oauth2/authorize",
        json={
            "action": "allow",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "state": "",
        },
    )
    assert resp.status_code == 401


# ── POST /oauth2/token ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_token_success(client):
    """正常 code 换 token → 返回 access_token。"""
    user_id = await _admin_user_id()
    code = await _insert_auth_code(user_id)

    resp = await _exchange_request(client, code=code)
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"]
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_token_replay(client):
    """相同 code 使用两次（防重放）→ 第二次返回 400 invalid_grant。"""
    user_id = await _admin_user_id()
    code = await _insert_auth_code(user_id)

    resp1 = await _exchange_request(client, code=code)
    assert resp1.status_code == 200

    resp2 = await _exchange_request(client, code=code)
    assert resp2.status_code == 400
    assert resp2.json()["detail"]["error"] == "invalid_grant"


@pytest.mark.asyncio
async def test_token_expired_code(client):
    """超过 TTL（10 分钟）的 code → 400 invalid_grant。"""
    user_id = await _admin_user_id()
    code = await _insert_auth_code(user_id, created_at=datetime.utcnow() - timedelta(minutes=11))

    resp = await _exchange_request(client, code=code)
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_grant"


@pytest.mark.asyncio
async def test_token_unknown_code(client):
    """从未签发过的 code → 400 invalid_grant。"""
    resp = await _exchange_request(client, code=secrets.token_hex(32))
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_grant"


@pytest.mark.asyncio
async def test_token_wrong_client_id(client):
    """client_id 不匹配 → 401 invalid_client。"""
    user_id = await _admin_user_id()
    code = await _insert_auth_code(user_id)

    resp = await _exchange_request(client, code=code, client_id="evil")
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "invalid_client"


@pytest.mark.asyncio
async def test_token_wrong_secret(client):
    """错误的 client_secret → 401 invalid_client。"""
    user_id = await _admin_user_id()
    code = await _insert_auth_code(user_id)

    resp = await _exchange_request(client, code=code, client_secret="wrong-secret")
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "invalid_client"


@pytest.mark.asyncio
async def test_token_unsupported_grant_type(client):
    """非 authorization_code → 400 unsupported_grant_type。"""
    resp = await _exchange_request(client, code="abc", grant_type="client_credentials")
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "unsupported_grant_type"


# ── GET /oauth2/userinfo ───────────────────────────────────────────────


async def _oauth2_token_for_admin() -> str:
    """为真实 admin 签发一个 OAuth2 access_token。"""
    from app.iam.tokens import TokenService

    user_id = await _admin_user_id()
    return TokenService.create_oauth2_access_token(user_id=user_id, username="admin")


@pytest.mark.asyncio
async def test_userinfo_valid_token(client):
    """有效的 OAuth2 access_token → 返回用户信息。"""
    token = await _oauth2_token_for_admin()

    resp = await client.get(
        "/api/v1/oauth2/userinfo",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "admin"
    assert data["login"] == "admin"
    assert data["name"] == "admin"
    assert data["id"]


@pytest.mark.asyncio
async def test_userinfo_no_bearer(client):
    """无 Authorization 头 → 401。"""
    resp = await client.get("/api/v1/oauth2/userinfo")
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "invalid_token"


@pytest.mark.asyncio
async def test_userinfo_garbage_token(client):
    """非 JWT 格式的 token → 401。"""
    resp = await client.get(
        "/api/v1/oauth2/userinfo",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_userinfo_wrong_token_type(client, admin_tokens):
    """用登录 JWT (type=access) 而非 OAuth2 JWT → 401。"""
    resp = await client.get(
        "/api/v1/oauth2/userinfo",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_userinfo_disabled_user(client):
    """用户被禁用后，已签发的 OAuth2 token 立即失效 → 401。"""
    token = await _oauth2_token_for_admin()

    # 禁用前 token 有效
    ok_resp = await client.get(
        "/api/v1/oauth2/userinfo", headers={"Authorization": f"Bearer {token}"}
    )
    assert ok_resp.status_code == 200

    user_id = await _admin_user_id()
    from app.services import get_user_backend

    await get_user_backend().update_user(uuid_mod.UUID(user_id), {"is_active": False})

    resp = await client.get(
        "/api/v1/oauth2/userinfo", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "invalid_token"


# ── 单元测试：TokenService.verify_oauth2_access_token ──────────────────


def _jwt_test_settings():
    """单元测试无 fixture，显式设置 JWT 相关配置。"""
    from app.config import settings

    settings.AGENTOS_JWT_SECRET_KEY = "test-secret-key"


def test_verify_oauth2_token_roundtrip():
    """create → verify 往返：payload 带 type=oauth2_access。"""
    _jwt_test_settings()
    from app.iam.tokens import TokenService

    token = TokenService.create_oauth2_access_token(
        user_id="00000000-0000-0000-0000-000000000001", username="admin"
    )
    payload = TokenService.verify_oauth2_access_token(token)
    assert payload is not None
    assert payload["type"] == "oauth2_access"
    assert payload["sub"] == "00000000-0000-0000-0000-000000000001"
    assert payload["username"] == "admin"


def test_verify_oauth2_token_rejects_login_jwt():
    """登录 JWT (type=access) 不能通过 OAuth2 校验 → None。"""
    _jwt_test_settings()
    from app.iam.tokens import TokenService

    token = TokenService.create_access_token(
        user_id="00000000-0000-0000-0000-000000000001", username="admin", role="admin"
    )
    assert TokenService.verify_oauth2_access_token(token) is None


def test_verify_oauth2_token_rejects_expired():
    """过期 token（require_exp）→ None。"""
    _jwt_test_settings()
    from app.config import settings
    from app.iam.tokens import TokenService

    original = settings.OAUTH2_ACCESS_TOKEN_EXPIRE_MINUTES
    settings.OAUTH2_ACCESS_TOKEN_EXPIRE_MINUTES = -1
    try:
        token = TokenService.create_oauth2_access_token(
            user_id="00000000-0000-0000-0000-000000000001", username="admin"
        )
        assert TokenService.verify_oauth2_access_token(token) is None
    finally:
        settings.OAUTH2_ACCESS_TOKEN_EXPIRE_MINUTES = original


def test_verify_oauth2_token_rejects_garbage():
    """非 JWT 字符串 → None（不抛异常）。"""
    _jwt_test_settings()
    from app.iam.tokens import TokenService

    assert TokenService.verify_oauth2_access_token("not-a-jwt") is None


# ── 单元测试：OAuth2Service.validate_client ────────────────────────────


def _oauth2_service_settings():
    """单元测试无 fixture，显式设置客户端配置。"""
    from app.config import settings

    settings.OAUTH2_CLIENT_ID = CLIENT_ID
    settings.OAUTH2_CLIENT_SECRET = CLIENT_SECRET


def test_validate_client_accepts_known_client():
    """凭据匹配 → 不抛异常。"""
    _oauth2_service_settings()
    from app.services.oauth_service import OAuth2Service

    OAuth2Service.validate_client(CLIENT_ID, CLIENT_SECRET)


@pytest.mark.parametrize(
    ("client_id", "client_secret"),
    [
        ("", CLIENT_SECRET),   # 空 client_id
        (CLIENT_ID, ""),       # 空 client_secret
        ("evil", CLIENT_SECRET),  # 未知 client_id
        (CLIENT_ID, "wrong"),  # 错误 client_secret
    ],
)
def test_validate_client_rejects_bad_credentials(client_id, client_secret):
    """凭据缺失/不匹配 → OAuth2Error(401, invalid_client)。"""
    _oauth2_service_settings()
    from app.services.oauth_service import OAuth2Error, OAuth2Service

    with pytest.raises(OAuth2Error) as exc_info:
        OAuth2Service.validate_client(client_id, client_secret)
    assert exc_info.value.status_code == 401
    assert exc_info.value.error == "invalid_client"


# ── 单元测试：OAuth2AuthorizationCode 模型 ─────────────────────────────


def test_auth_code_is_expired():
    """TTL 边界：10 分钟内有效，超过即过期。"""
    from app.models.oauth2_auth_code import OAuth2AuthorizationCode

    fresh = OAuth2AuthorizationCode(created_at=datetime.utcnow())
    assert fresh.is_expired() is False

    stale = OAuth2AuthorizationCode(
        created_at=datetime.utcnow() - timedelta(minutes=11)
    )
    assert stale.is_expired() is True


@pytest.mark.asyncio
async def test_auth_code_consume_is_one_shot(client):
    """consume 原子删除：第二次消费同一 code 返回 None。"""
    import app.database as _db
    from app.models.oauth2_auth_code import OAuth2AuthorizationCode

    user_id = await _admin_user_id()
    async with _db.async_session_maker() as session:
        entry = await OAuth2AuthorizationCode.create(
            session, user_id=uuid_mod.UUID(user_id),
            client_id=CLIENT_ID, redirect_uri=REDIRECT_URI,
        )
        code = entry.code

    async with _db.async_session_maker() as session:
        first = await OAuth2AuthorizationCode.consume(session, code)
        assert first is not None
        assert first.code == code

    async with _db.async_session_maker() as session:
        assert await OAuth2AuthorizationCode.consume(session, code) is None


@pytest.mark.asyncio
async def test_auth_code_delete_expired(client):
    """delete_expired 只清理过期记录，保留有效记录。"""
    import app.database as _db
    from app.models.oauth2_auth_code import OAuth2AuthorizationCode

    user_id = await _admin_user_id()
    async with _db.async_session_maker() as session:
        session.add(
            OAuth2AuthorizationCode(
                code=secrets.token_hex(32),
                user_id=uuid_mod.UUID(user_id),
                client_id=CLIENT_ID,
                redirect_uri=REDIRECT_URI,
                created_at=datetime.utcnow() - timedelta(minutes=11),
            )
        )
        fresh_code = secrets.token_hex(32)
        session.add(
            OAuth2AuthorizationCode(
                code=fresh_code,
                user_id=uuid_mod.UUID(user_id),
                client_id=CLIENT_ID,
                redirect_uri=REDIRECT_URI,
                created_at=datetime.utcnow(),
            )
        )
        await session.commit()

    async with _db.async_session_maker() as session:
        deleted = await OAuth2AuthorizationCode.delete_expired(session)
        assert deleted == 1

        # 有效记录仍在
        remaining = await OAuth2AuthorizationCode.consume(session, fresh_code)
        assert remaining is not None
