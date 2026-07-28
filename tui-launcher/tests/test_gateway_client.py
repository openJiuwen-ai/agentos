"""测试 gateway WebSocket 客户端的响应解析。

只测试纯解析逻辑（不测试实际 WS 连接，避免网络依赖）。
"""

import pytest

from agentos_tui_launcher import errors
from agentos_tui_launcher.gateway_client import SshEndpoint, WebSocketGatewayClient


class TestParseResponse:
    @staticmethod
    def test_valid_response():
        raw = '{"ok": true, "ssh_ip": "10.0.0.1", "ssh_port": 2222}'
        endpoint = WebSocketGatewayClient.parse_response(raw, request_id="test")
        assert endpoint == SshEndpoint(ssh_ip="10.0.0.1", ssh_port=2222)

    @staticmethod
    def test_response_as_bytes():
        raw = b'{"ok": true, "ssh_ip": "10.0.0.1", "ssh_port": 2222}'
        endpoint = WebSocketGatewayClient.parse_response(raw, request_id="test")
        assert endpoint.ssh_ip == "10.0.0.1"
        assert endpoint.ssh_port == 2222

    @staticmethod
    def test_ok_false_raises():
        raw = '{"ok": false, "error": "agent unavailable"}'
        with pytest.raises(errors.GatewayError, match="agent unavailable"):
            WebSocketGatewayClient.parse_response(raw, request_id="test")

    @staticmethod
    def test_ok_false_unknown_error():
        raw = '{"ok": false}'
        with pytest.raises(errors.GatewayError, match="未知错误"):
            WebSocketGatewayClient.parse_response(raw, request_id="test")

    @staticmethod
    def test_invalid_json_raises():
        raw = "not json at all"
        with pytest.raises(errors.GatewayError, match="不是有效 JSON"):
            WebSocketGatewayClient.parse_response(raw, request_id="test")

    @staticmethod
    def test_non_object_json_raises():
        raw = "[1, 2, 3]"
        with pytest.raises(errors.GatewayError, match="不是 JSON 对象"):
            WebSocketGatewayClient.parse_response(raw, request_id="test")

    @staticmethod
    def test_missing_ssh_ip_raises():
        raw = '{"ok": true, "ssh_port": 2222}'
        with pytest.raises(errors.GatewayError, match="ssh_ip"):
            WebSocketGatewayClient.parse_response(raw, request_id="test")

    @staticmethod
    def test_missing_ssh_port_raises():
        raw = '{"ok": true, "ssh_ip": "10.0.0.1"}'
        with pytest.raises(errors.GatewayError, match="ssh_port"):
            WebSocketGatewayClient.parse_response(raw, request_id="test")

    @staticmethod
    def test_empty_ssh_ip_raises():
        raw = '{"ok": true, "ssh_ip": "", "ssh_port": 2222}'
        with pytest.raises(errors.GatewayError, match="ssh_ip"):
            WebSocketGatewayClient.parse_response(raw, request_id="test")

    @staticmethod
    def test_zero_ssh_port_raises():
        raw = '{"ok": true, "ssh_ip": "10.0.0.1", "ssh_port": 0}'
        with pytest.raises(errors.GatewayError, match="ssh_port"):
            WebSocketGatewayClient.parse_response(raw, request_id="test")

    @staticmethod
    def test_negative_ssh_port_raises():
        raw = '{"ok": true, "ssh_ip": "10.0.0.1", "ssh_port": -1}'
        with pytest.raises(errors.GatewayError, match="ssh_port"):
            WebSocketGatewayClient.parse_response(raw, request_id="test")


class TestBuildHeaders:
    @staticmethod
    def test_both_token_and_user_id():
        headers = WebSocketGatewayClient.build_headers(
            token="abc123", user_id="user-1"
        )
        assert headers["Authorization"] == "Bearer abc123"
        assert headers["X-User-Id"] == "user-1"

    @staticmethod
    def test_token_only():
        headers = WebSocketGatewayClient.build_headers(token="abc123", user_id=None)
        assert headers["Authorization"] == "Bearer abc123"
        assert "X-User-Id" not in headers

    @staticmethod
    def test_user_id_only():
        headers = WebSocketGatewayClient.build_headers(token=None, user_id="user-1")
        assert "Authorization" not in headers
        assert headers["X-User-Id"] == "user-1"

    @staticmethod
    def test_neither_returns_empty():
        headers = WebSocketGatewayClient.build_headers(token=None, user_id=None)
        assert headers == {}

    @staticmethod
    def test_empty_token_not_included():
        headers = WebSocketGatewayClient.build_headers(token="", user_id="user-1")
        assert "Authorization" not in headers
        assert headers["X-User-Id"] == "user-1"
