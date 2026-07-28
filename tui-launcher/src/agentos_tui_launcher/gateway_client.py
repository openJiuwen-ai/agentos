"""gateway WebSocket 客户端。

新设计（tui-switch-cc-design-new.md 第 10.3 节）下，launcher 收到 handoff 消息后：

1. 向 gateway 建立 WebSocket 连接
2. 等待 gateway 推送的 `connection.ack` 事件
3. 调用 `3rdagent.switch` 方法
4. 获取返回的 SSH IP 和 Port（或 sandbox_id，取决于 gateway 版本）

本模块使用 `websockets` 库实现 WS 通信。websockets 为可选依赖，
缺失时在运行时抛出 GatewayError。

WS 消息格式（launcher <-> gateway），见 tui-switch-cc-launcher-interface.md 第 5 节：

连接后 gateway 先推送 connection.ack 事件：
    {"type": "event", "event": "connection.ack"}

请求（launcher -> gateway）：
    {
        "type": "req",
        "id": "<uuid>",
        "method": "3rdagent.switch",
        "params": {"agent_type": "claude", "session_id": "<session_id>"}
    }

成功响应（gateway -> launcher）：
    {
        "type": "res",
        "id": "<同请求id>",
        "ok": true,
        "payload": {"ssh_ip": "192.168.x.x", "ssh_port": 22}
    }

失败响应（gateway -> launcher）：
    {
        "type": "res",
        "id": "<同请求id>",
        "ok": false,
        "error": "错误描述",
        "code": "BAD_REQUEST"
    }
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Optional, Protocol

from . import errors


@dataclass(frozen=True)
class SshEndpoint:
    """gateway 返回的 SSH 连接端点。"""

    ssh_ip: str
    ssh_port: int


class GatewayClient(Protocol):
    """gateway WS 客户端协议。"""

    def switch(
        self,
        gateway_url: str,
        agent_type: str,
        session_id: str,
        token: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> SshEndpoint:
        ...


class WebSocketGatewayClient:
    """基于 websockets 库的 GatewayClient 实现。

    - 连接 gateway WS，发送 3rdagent.switch 请求。
    - 携带 access token 与 user_id 用于身份绑定。
    - 返回 SSH 端点。
    """

    def switch(
        self,
        gateway_url: str,
        agent_type: str,
        session_id: str,
        token: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> SshEndpoint:
        """连接 gateway 并调用 3rdagent.switch。

        Args:
            gateway_url: gateway WS 地址。
            agent_type: 三方 Agent 类型（取自 handoff JSON 的 parsed 字段）。
            session_id: 当前会话 ID。
            token: access token，用于 WS 连接头身份绑定。
            user_id: 用户 ID，用于 WS 连接头身份绑定。

        Raises:
            GatewayError: WS 连接失败、消息格式错误或 gateway 返回错误。
        """
        try:
            import asyncio

            import websockets
        except ImportError as exc:
            raise errors.GatewayError(
                "websockets 库未安装，无法连接 gateway。"
            ) from exc

        # 生成请求 ID（UUID），用于请求-响应匹配。
        request_id = str(uuid.uuid4())

        request = {
            "type": "req",
            "id": request_id,
            "method": "3rdagent.switch",
            "params": {
                "agent_type": agent_type,
                "session_id": session_id,
            },
        }

        # 构造 WS 连接头：携带 token 和 user_id 用于身份绑定。
        headers = self.build_headers(token=token, user_id=user_id)

        # websockets 14+ 用 additional_headers，12-13 用 extra_headers。
        _ws_major = int(websockets.__version__.split(".")[0])
        if _ws_major >= 14:
            _connect_kwargs = {"additional_headers": headers}
        else:
            _connect_kwargs = {"extra_headers": headers}

        async def _do_switch() -> SshEndpoint:
            try:
                async with websockets.connect(
                    gateway_url,
                    open_timeout=10,
                    close_timeout=5,
                    **_connect_kwargs,
                ) as ws:
                    # 1. 等待 gateway 推送 connection.ack 事件
                    await self._wait_for_connection_ack(ws, timeout=10)

                    # 2. 发送 3rdagent.switch 请求
                    try:
                        await ws.send(json.dumps(request))
                    except Exception as exc:
                        raise errors.GatewayError(
                            f"发送 3rdagent.switch 请求失败: "
                            f"{type(exc).__name__}: {exc}"
                        ) from exc

                    # 3. 等待匹配请求 id 的响应
                    raw_response = await self._wait_for_response(
                        ws, request_id, timeout=120
                    )
            except errors.GatewayError:
                raise
            except websockets.exceptions.InvalidStatus as exc:
                # HTTP 握手阶段被拒绝（如 401/403/404）
                raise errors.GatewayError(
                    f"gateway WS 握手失败，HTTP 状态码: {exc.response.status_code} "
                    f"{exc.response.reason_phrase}。"
                    f"请检查 gateway_url、token、user_id 是否正确。"
                ) from exc
            except websockets.exceptions.InvalidURI as exc:
                raise errors.GatewayError(
                    f"gateway_url 格式无效: {exc}"
                ) from exc
            except websockets.exceptions.WebSocketException as exc:
                raise errors.GatewayError(
                    f"gateway WS 协议错误: {type(exc).__name__}: {exc}"
                ) from exc
            except OSError as exc:
                raise errors.GatewayError(
                    f"gateway 网络连接失败: {type(exc).__name__}: {exc}。"
                    f"请检查 gateway 服务是否启动、端口是否可达。"
                ) from exc
            except Exception as exc:
                raise errors.GatewayError(
                    f"gateway WS 连接或通信失败: {type(exc).__name__}: {exc}"
                ) from exc

            return self.parse_response(raw_response, request_id)

        try:
            return asyncio.run(_do_switch())
        except errors.GatewayError:
            raise
        except Exception as exc:
            raise errors.GatewayError(
                f"gateway WS 调用失败: {type(exc).__name__}"
            ) from exc

    async def _wait_for_connection_ack(self, ws, timeout: float) -> None:
        """等待 gateway 推送 connection.ack 事件。

        gateway 连接建立后会先推送：
            {"type": "event", "event": "connection.ack"}

        必须收到此事件后才能发送业务请求。

        Raises:
            GatewayError: 超时未收到 ack，或收到非预期消息。
        """
        import asyncio
        import websockets.exceptions

        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise errors.GatewayError(
                "等待 gateway connection.ack 超时。"
            ) from exc
        except websockets.exceptions.ConnectionClosed as exc:
            # gateway 主动关闭连接，显示 close code 和 reason 帮助诊断
            raise errors.GatewayError(
                f"gateway 在发送 connection.ack 前关闭连接: "
                f"code={exc.code}, reason={exc.reason!r}。"
                f"请检查 gateway_url 是否正确、gateway 服务是否正常。"
            ) from exc
        except Exception as exc:
            raise errors.GatewayError(
                f"等待 connection.ack 时 WS 错误: {type(exc).__name__}: {exc}"
            ) from exc

        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise errors.GatewayError(
                "gateway connection.ack 消息不是有效 JSON。"
            ) from exc

        if (
            not isinstance(msg, dict)
            or msg.get("type") != "event"
            or msg.get("event") != "connection.ack"
        ):
            raise errors.GatewayError(
                f"gateway 未发送 connection.ack，收到: {msg}"
            )

    async def _wait_for_response(self, ws, request_id: str, timeout: float):
        """等待匹配请求 id 的响应消息，跳过事件消息。

        gateway 可能推送其他事件（如 session 更新），只处理 type=res
        且 id 匹配的消息。

        Raises:
            GatewayError: 超时未收到匹配响应。
        """
        import asyncio

        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise errors.GatewayError(
                    "等待 3rdagent.switch 响应超时。"
                )
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError as exc:
                raise errors.GatewayError(
                    "等待 3rdagent.switch 响应超时。"
                ) from exc
            except Exception as exc:
                raise errors.GatewayError(
                    f"等待响应时 WS 错误: {type(exc).__name__}: {exc}"
                ) from exc

            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue

            if (
                isinstance(msg, dict)
                and msg.get("type") == "res"
                and msg.get("id") == request_id
            ):
                return raw

    @staticmethod
    def build_headers(
        token: Optional[str],
        user_id: Optional[str],
    ) -> dict[str, str]:
        """构造 WS 连接头。

        携带 Authorization（Bearer token）和 X-User-Id，
        与 jiuwenswarm-tui 连接 gateway 时的身份绑定方式一致。
        """
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if user_id:
            headers["X-User-Id"] = user_id
        return headers

    @staticmethod
    def parse_response(
        raw_response: str | bytes,
        request_id: str,
    ) -> SshEndpoint:
        """解析 gateway 返回的 WS 消息。

        期望格式（见 tui-switch-cc-launcher-interface.md 第 5.2/5.3 节）：
            {"type": "res", "id": "...", "ok": true, "payload": {"ssh_ip": "...", "ssh_port": 22}}
            {"type": "res", "id": "...", "ok": false, "error": "...", "code": "BAD_REQUEST"}
        """
        if isinstance(raw_response, bytes):
            raw_response = raw_response.decode("utf-8", errors="replace")

        try:
            data = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise errors.GatewayError(
                "gateway 返回的消息不是有效 JSON。"
            ) from exc

        if not isinstance(data, dict):
            raise errors.GatewayError("gateway 返回的消息不是 JSON 对象。")

        # 校验响应 type（宽松：缺失时不报错，存在时必须是 "res"）。
        resp_type = data.get("type")
        if resp_type is not None and resp_type != "res":
            raise errors.GatewayError(
                f"gateway 返回的 type 不是 'res'，实际为 '{resp_type}'。"
            )

        if not data.get("ok", False):
            error_msg = data.get("error", "未知错误")
            error_code = data.get("code")
            if error_code:
                raise errors.GatewayError(
                    f"gateway 拒绝切换请求: {error_msg} (code={error_code})"
                )
            raise errors.GatewayError(f"gateway 拒绝切换请求: {error_msg}")

        # 新格式：ssh_ip/ssh_port 在 payload 对象里。
        payload = data.get("payload")
        if isinstance(payload, dict):
            ssh_ip = payload.get("ssh_ip")
            ssh_port = payload.get("ssh_port")
        else:
            # 兼容旧格式（顶层 ssh_ip/ssh_port）。
            ssh_ip = data.get("ssh_ip")
            ssh_port = data.get("ssh_port")

        if not isinstance(ssh_ip, str) or not ssh_ip:
            # 显示实际 payload 帮助调试契约差异
            payload_str = json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else str(payload)
            raise errors.GatewayError(
                f"gateway 返回的 ssh_ip 缺失或无效。"
                f"实际 payload: {payload_str}"
            )
        if not isinstance(ssh_port, int) or ssh_port <= 0:
            payload_str = json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else str(payload)
            raise errors.GatewayError(
                f"gateway 返回的 ssh_port 缺失或无效。"
                f"实际 payload: {payload_str}"
            )

        return SshEndpoint(ssh_ip=ssh_ip, ssh_port=ssh_port)
