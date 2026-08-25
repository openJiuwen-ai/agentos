"""Tests for auth.py — JWT verification via control-panel."""

import json
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

import auth
from auth import TokenData, require_admin


# ── TokenData ────────────────────────────────────────────────────────────


class TestTokenData:
    @staticmethod
    def test_fields():
        td = TokenData(user_id="u1", username="admin", role="admin")
        assert td.user_id == "u1"
        assert td.username == "admin"
        assert td.role == "admin"


# ── verify_token ─────────────────────────────────────────────────────────


class TestVerifyToken:
    """Tests for the synchronous verify_token function."""

    @staticmethod
    def _make_response(data: dict):
        body = json.dumps({"code": 200, "data": data}).encode()
        resp = MagicMock()
        resp.read.return_value = body
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    @staticmethod
    @patch("auth.urllib.request.urlopen")
    def test_valid_admin_token(mock_urlopen):
        mock_urlopen.return_value = TestVerifyToken._make_response({
            "valid": True, "authorized": True,
            "user_id": "u1", "username": "admin", "role": "admin",
        })
        result = auth.verify_token("valid-token")
        assert result.user_id == "u1"
        assert result.username == "admin"
        assert result.role == "admin"

    @staticmethod
    @patch("auth.urllib.request.urlopen")
    def test_invalid_token(mock_urlopen):
        mock_urlopen.return_value = TestVerifyToken._make_response({
            "valid": False, "authorized": False,
        })
        with pytest.raises(HTTPException) as exc_info:
            auth.verify_token("bad-token")
        assert exc_info.value.status_code == 401

    @staticmethod
    @patch("auth.urllib.request.urlopen")
    def test_non_admin_role(mock_urlopen):
        mock_urlopen.return_value = TestVerifyToken._make_response({
            "valid": True, "authorized": False, "role": "user",
        })
        with pytest.raises(HTTPException) as exc_info:
            auth.verify_token("user-token")
        assert exc_info.value.status_code == 403

    @staticmethod
    @patch("auth.urllib.request.urlopen",
           side_effect=urllib.error.URLError(ConnectionRefusedError()))
    def test_connection_refused(mock_urlopen):
        with pytest.raises(HTTPException) as exc_info:
            auth.verify_token("token")
        assert exc_info.value.status_code == 502

    @staticmethod
    @patch("auth.urllib.request.urlopen", side_effect=TimeoutError)
    def test_timeout(mock_urlopen):
        with pytest.raises(HTTPException) as exc_info:
            auth.verify_token("token")
        assert exc_info.value.status_code == 504

    @staticmethod
    @patch("auth.urllib.request.urlopen")
    def test_non_200_response(mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="", code=500, msg="Internal Server Error",
            hdrs=None, fp=BytesIO(b'{}'),
        )
        with pytest.raises(HTTPException) as exc_info:
            auth.verify_token("token")
        assert exc_info.value.status_code == 502


# ── require_admin (FastAPI dependency) ───────────────────────────────────


class TestRequireAdmin:
    """Test require_admin as a FastAPI dependency via TestClient."""

    @staticmethod
    def _make_app():
        app = FastAPI()

        @app.get("/protected")
        async def protected(_user: TokenData = Depends(require_admin)):
            return {"user": _user.username}

        return app

    @staticmethod
    def test_no_credentials_returns_401():
        app = TestRequireAdmin._make_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/protected")
        assert resp.status_code == 401

    @staticmethod
    @patch("auth.verify_token")
    def test_valid_token_returns_200(mock_verify):
        mock_verify.return_value = TokenData("u1", "admin", "admin")
        app = TestRequireAdmin._make_app()
        client = TestClient(app)
        resp = client.get("/protected", headers={"Authorization": "Bearer test-token"})
        assert resp.status_code == 200
        assert resp.json()["user"] == "admin"
        mock_verify.assert_called_once_with("test-token")


# ── Integration: full verify flow ────────────────────────────────────────


class TestVerifyFlow:
    """End-to-end: HTTP request → require_admin → urllib → response."""

    @staticmethod
    def _make_app():
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint(_user: TokenData = Depends(require_admin)):
            return {"user_id": _user.user_id, "role": _user.role}

        return app

    @staticmethod
    @patch("auth.urllib.request.urlopen")
    def test_full_flow_valid(mock_urlopen):
        body = json.dumps({
            "code": 200,
            "data": {
                "valid": True, "authorized": True,
                "user_id": "u-42", "username": "admin", "role": "admin",
            },
        }).encode()
        resp = MagicMock()
        resp.read.return_value = body
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        app = TestVerifyFlow._make_app()
        client = TestClient(app)
        r = client.get("/test", headers={"Authorization": "Bearer real-token"})
        assert r.status_code == 200
        assert r.json()["user_id"] == "u-42"

    @staticmethod
    @patch("auth.urllib.request.urlopen")
    def test_full_flow_invalid(mock_urlopen):
        body = json.dumps({
            "code": 200,
            "data": {"valid": False, "authorized": False},
        }).encode()
        resp = MagicMock()
        resp.read.return_value = body
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        app = TestVerifyFlow._make_app()
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/test", headers={"Authorization": "Bearer bad-token"})
        assert r.status_code == 401
