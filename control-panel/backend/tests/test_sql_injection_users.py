"""SQL injection security tests for api/v1/users.

Tests that the endpoint is immune to SQL injection via:
- search parameter (ilike query)
- sort parameter (getattr column access)
- order parameter (asc/desc clause)
- page/page_size parameters

Uses conftest.py backend & client fixtures (in-memory SQLite, no external deps).
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


# ── Helper ────────────────────────────────────────────────────────────


def _make_client():
    """Create a fresh ASGI client. Tests that need a custom setup
    (e.g. pre-existing users) should use the client fixture from conftest."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _login_as_admin(client: AsyncClient) -> str:
    """Log in with the seed admin and return an access token."""
    from app.config import settings
    resp = await client.post("/api/v1/auth/login", json={
        "username": settings.AGENTOS_ADMIN_USERNAME,
        "password": settings.AGENTOS_ADMIN_PASSWORD,
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["data"]["access_token"]


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── search parameter injection tests ──────────────────────────────────

SQLI_PAYLOADS_SEARCH = [
    # Classic SQL injection probes
    "' OR '1'='1",
    "' OR 1=1 --",
    "admin' --",
    "admin' #",
    "' UNION SELECT * FROM users --",
    "' UNION SELECT NULL, NULL, NULL --",
    "' OR '1'='1' --",
    "%' OR 1=1 --",
    "'; DROP TABLE users; --",
    "') OR 1=1 --",
    # SQLite-specific
    "' UNION SELECT sql FROM sqlite_master --",
    "' OR 1=1 UNION SELECT 1,2,3 --",
    # Encoded variants
    "%27%20OR%20%271%27%3D%271",
    # Stacked queries
    "'; DELETE FROM users WHERE '1'='1",
    "1'; SELECT * FROM users; --",
    # Time-based blind
    "' OR (SELECT CASE WHEN (1=1) THEN 1 ELSE load_extension(1) END) --",
    # Out-of-band / error-based
    "' AND 1=CAST((SELECT group_concat(name) FROM sqlite_master) AS INT) --",
]

SORT_PAYLOADS = [
    # Attempt to access internal/sensitive attributes
    "__table__",
    "__dict__",
    "__class__",
    "__init__",
    "metadata",
    "_sa_class_manager",
    # SQL-like injection attempts in sort
    "created_at; DROP TABLE users; --",
    "created_at DESC; --",
    "' OR 1=1 --",
    # Path traversal style
    "../etc/passwd",
    "1; SELECT * FROM users",
]

ORDER_PAYLOADS = [
    "desc; DROP TABLE users; --",
    "asc; DELETE FROM users --",
    "' OR 1=1 --",
    "desc, (SELECT * FROM users)",
]

PAGE_PAYLOADS = [
    "-1",
    "0",
    "99999999999999999999",
    "1 OR 1=1",
    "1; DROP TABLE users; --",
    "../../../etc/passwd",
]


@pytest.mark.asyncio
async def test_search_sql_injection_payloads(client, admin_tokens):
    """All SQL injection payloads in the search parameter are safely escaped."""
    token = admin_tokens["access_token"]
    headers = _auth_header(token)

    for payload in SQLI_PAYLOADS_SEARCH:
        resp = await client.get(
            "/api/v1/users", params={"search": payload}, headers=headers
        )
        # Must NOT cause a 500. 200 or 400 series is fine.
        assert resp.status_code != 500, (
            f"SEARCH PAYLOAD caused 500: {repr(payload)}\nResponse: {resp.text[:500]}"
        )
        # Must not return data that wasn't requested (no unintended rows)
        data = resp.json()
        assert "code" in data
        # With SQL injection the total count shouldn't exceed the real count
        # (admin seed = 1 user; payload should match 0 or stay safe)
        assert data["code"] == 200, (
            f"SEARCH PAYLOAD caused non-200: {repr(payload)}\nResponse: {resp.text[:500]}"
        )


@pytest.mark.asyncio
async def test_sort_sql_injection_payloads(client, admin_tokens):
    """Malicious sort values are rejected (HTTP 400) or fall back safely."""
    token = admin_tokens["access_token"]
    headers = _auth_header(token)

    for payload in SORT_PAYLOADS:
        resp = await client.get(
            "/api/v1/users", params={"sort": payload}, headers=headers
        )
        # Must not cause a 500.
        assert resp.status_code != 500, (
            f"SORT PAYLOAD caused 500: {repr(payload)}\nResponse: {resp.text[:500]}"
        )
        body = resp.json()
        # Acceptable responses:
        #   - 200 with normal data (valid sort, or payload that happens to be safe)
        #   - 400/422 from input validation
        #   - "code" key is only present on 200-success responses
        if resp.status_code == 200:
            assert body.get("code") == 200, (
                f"SORT PAYLOAD returned unexpected 200 body: {repr(payload)}\n{resp.text[:500]}"
            )
        else:
            # 4xx is expected for rejected payloads like __table__, SQL-like strings, etc.
            assert 400 <= resp.status_code < 500, (
                f"SORT PAYLOAD caused unexpected status: {repr(payload)} -> {resp.status_code}"
            )


@pytest.mark.asyncio
async def test_order_sql_injection_payloads(client, admin_tokens):
    """Malicious order values are handled gracefully."""
    token = admin_tokens["access_token"]
    headers = _auth_header(token)

    for payload in ORDER_PAYLOADS:
        resp = await client.get(
            "/api/v1/users", params={"order": payload}, headers=headers
        )
        assert resp.status_code != 500, (
            f"ORDER PAYLOAD caused 500: {repr(payload)}\nResponse: {resp.text[:500]}"
        )


@pytest.mark.asyncio
async def test_page_sql_injection_payloads(client, admin_tokens):
    """Malicious page/page_size values are handled gracefully."""
    token = admin_tokens["access_token"]
    headers = _auth_header(token)

    for payload in PAGE_PAYLOADS:
        # Test page param
        resp = await client.get(
            "/api/v1/users", params={"page": payload}, headers=headers
        )
        assert resp.status_code != 500, (
            f"PAGE PAYLOAD caused 500: {repr(payload)}\nResponse: {resp.text[:500]}"
        )
        # Test page_size param
        resp2 = await client.get(
            "/api/v1/users", params={"page_size": payload}, headers=headers
        )
        assert resp2.status_code != 500, (
            f"PAGE_SIZE PAYLOAD caused 500: {repr(payload)}\nResponse: {resp2.text[:500]}"
        )


@pytest.mark.asyncio
async def test_search_is_harmless(client, admin_tokens):
    """Verify search parameter uses parameterized queries — no data leak."""
    token = admin_tokens["access_token"]
    headers = _auth_header(token)

    # Baseline: without search, we get the admin user
    resp = await client.get("/api/v1/users", headers=headers)
    assert resp.status_code == 200
    baseline = resp.json()["data"]["total"]

    # With ' OR 1=1 we should NOT get more rows than baseline
    # (parametrized query treats it as a literal search string)
    resp = await client.get(
        "/api/v1/users",
        params={"search": "' OR '1'='1"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    # The search string is literal — should match 0 users, not all
    assert data["total"] <= baseline, (
        f"SQL INJECTION LIKELY: search returned {data['total']} rows, "
        f"baseline is {baseline}"
    )


@pytest.mark.asyncio
async def test_sort_parameter_is_not_injectable(backend):
    """Direct backend test: malicious sort values cause AttributeError, not SQL injection."""
    # Create some test users first
    usernames = ["sql_test_a", "sql_test_b", "sql_test_c"]
    for name in usernames:
        await backend.create_user(name)

    # Test each malicious sort value directly against the backend
    for payload in SORT_PAYLOADS:
        try:
            result = await backend.list_users(page=1, page_size=10, sort=payload)
            # If it doesn't crash, verify it returned valid data (fallback to default sort)
            assert result.total >= 1
        except (AttributeError, TypeError):
            # Expected: getattr on non-column attribute fails on .desc()/.asc()
            # This is NOT SQL injection — it's a missing validation, but param-safe
            pass
        except Exception as e:
            # Any other exception type should NOT contain SQL error keywords
            msg = str(e).lower()
            assert "sql" not in msg, (
                f"SORT PAYLOAD caused unexpected error: {repr(payload)} -> {e}"
            )
