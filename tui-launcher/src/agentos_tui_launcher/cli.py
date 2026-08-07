"""agentos-tui 命令行入口。

公共契约第 4.10 节定义本模块行为。

稳定命令表面：
    agentos-tui            # 恢复登录态或引导登录，然后启动主 TUI
    agentos-tui login      # 在普通终端登录，不启动 TUI
    agentos-tui logout     # 调用服务端 logout 并清除本地凭据
    agentos-tui whoami     # 显示当前身份

launcher 自有参数：
    --api-url <url>        # IAM / User API 基础地址
    --no-save-login        # 仅本次会话登录，不写入安全凭据存储
    --                     # 分隔符；后续元素只属于 JiuwenSwarm

退出码：
    0  = launcher 自有命令成功
    2  = CLI 用法或参数契约错误
    3  = 无法建立认证身份
    4  = 配置或安全凭据错误
    5  = 必需可执行文件或 handoff 目标不可用
    6  = 网络或远端服务错误
    70 = 未分类内部错误
"""

from __future__ import annotations

import getpass
import logging
import os
import sys
import time
import uuid
from typing import Optional

from . import errors
from .argv_adapter import LauncherArgvAdapter, LauncherArgvAdapterImpl, TuiArgvAnalysis
from .auth_client import RequestsAuthClient
from .config import ClientConfig, FileConfigStore
from .credential_store import FileCredentialStore, KeyringCredentialStore
from .gateway_client import GatewayClient, WebSocketGatewayClient
from .handoff import parse_handoff_stdout
from .protocol import HandoffAction, LaunchMode, TuiTarget
from .resolver import ExecutableResolverImpl, ResolvedExecutable
from .ssh_tunnel import ParamikoSshTunnelClient, SshTunnelClient
from .supervisor import (
    SubprocessRunner,
    SupervisedProcessResult,
    SupervisionProtocol,
    TuiSupervisor,
)
from .user_context import SessionServiceImpl, UserContext


# ============================================================================
# 退出码常量
# ============================================================================


EXIT_OK = 0
EXIT_USAGE = 2
EXIT_AUTH = 3
EXIT_CONFIG = 4
EXIT_EXECUTABLE = 5
EXIT_NETWORK = 6
EXIT_INTERNAL = 70


# ============================================================================
# 循环保护常量
# ============================================================================


# 任意滚动 60 秒窗口内最多自动处理一次 REAUTH_REQUIRED。
REAUTH_WINDOW_SECONDS = 60.0
REAUTH_MAX_IN_WINDOW = 1

# 任意滚动 60 秒窗口内最多切回 5 次，防止主 TUI ↔ cc-tui 之间无限切换。
SWITCH_LOOP_WINDOW_SECONDS = 60.0
SWITCH_LOOP_MAX_IN_WINDOW = 5


# ============================================================================
# 主入口
# ============================================================================


def main(argv: Optional[list[str]] = None) -> int:
    """agentos-tui 命令行入口。

    返回退出码；由 __main__.py / console script 透传给 sys.exit。
    """
    if argv is None:
        # sys.argv[0] 是脚本名，跳过。
        argv = sys.argv[1:]

    cli = LauncherCli()
    return cli.run(tuple(argv))


# ============================================================================
# LauncherCli
# ============================================================================


class LauncherCli:
    """launcher 主类，负责参数分流与流程编排。

    所有依赖在构造时注入，便于测试。
    """

    def __init__(
        self,
        *,
        stdin: Optional[object] = None,
        stdout: Optional[object] = None,
        stderr: Optional[object] = None,
    ) -> None:
        # 默认使用 sys.stdin/out/err；可注入便于测试。
        self._stdin = stdin or sys.stdin
        self._stdout = stdout or sys.stdout
        self._stderr = stderr or sys.stderr

        self._out_logger = self._build_cli_logger(self._stdout)
        self._err_logger = self._build_cli_logger(self._stderr)

    @staticmethod
    def _build_cli_logger(stream) -> logging.Logger:
        logger = logging.getLogger(f"cli_{id(stream)}")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
        return logger

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def run(self, argv: tuple[str, ...]) -> int:
        """处理 argv 并返回退出码。"""
        try:
            return self._dispatch(argv)
        except errors.UsageError as exc:
            self._err(f"Usage error: {exc}")
            return EXIT_USAGE
        except errors.ConfigError as exc:
            self._err(f"Config error: {exc}")
            return EXIT_CONFIG
        except errors.CredentialStoreUnavailable as exc:
            self._err(f"Credential store unavailable: {exc}")
            return EXIT_CONFIG
        except errors.CredentialCorrupted as exc:
            self._err(f"Credential corrupted: {exc}")
            return EXIT_CONFIG
        except errors.InvalidCredentials as exc:
            self._err(f"Invalid credentials: {exc}")
            return EXIT_AUTH
        except errors.AuthenticationExpired as exc:
            self._err(f"Authentication expired: {exc}")
            return EXIT_AUTH
        except errors.PermissionDenied as exc:
            self._err(f"Permission denied: {exc}")
            return EXIT_AUTH
        except errors.NetworkUnavailable as exc:
            self._err(f"Network unavailable: {exc}")
            return EXIT_NETWORK
        except errors.RemoteServiceError as exc:
            self._err(f"Remote service error: {exc}")
            return EXIT_NETWORK
        except errors.RemoteContractError as exc:
            self._err(f"Remote contract error: {exc}")
            return EXIT_NETWORK
        except errors.ExecutableUnavailable as exc:
            self._err(f"Executable unavailable: {exc}")
            return EXIT_EXECUTABLE
        except errors.ReauthenticationLoop as exc:
            self._err(f"Reauthentication loop: {exc}")
            return EXIT_AUTH
        except errors.LauncherError as exc:
            self._err(f"Error: {exc}")
            return EXIT_INTERNAL
        except KeyboardInterrupt:
            self._err("Interrupted by user.")
            return EXIT_AUTH
        except Exception as exc:  # pragma: no cover - 防御性处理
            import traceback
            self._err(f"Internal error: {type(exc).__module__}.{type(exc).__name__}: {exc}")
            self._err(f"Traceback:\n{traceback.format_exc()}")
            return EXIT_INTERNAL

    # ------------------------------------------------------------------
    # 命令分发
    # ------------------------------------------------------------------

    def _dispatch(self, argv: tuple[str, ...]) -> int:
        """根据子命令分发。"""
        if not argv:
            return self._cmd_default(())

        first = argv[0]

        # 帮助与版本在任何情况下都不需要 service URL，提前拦截。
        if first in ("-h", "--help"):
            return self._print_help()
        if first in ("-V", "--version"):
            from . import __version__

            self._out(f"agentos-tui {__version__}")
            return EXIT_OK

        if first.startswith("-"):
            # 没有子命令；按默认启动处理，整个 argv 作为 launcher 参数 + TUI 参数。
            return self._cmd_default(argv)

        if first == "login":
            return self._cmd_login(argv[1:])
        if first == "logout":
            return self._cmd_logout(argv[1:])
        if first == "whoami":
            return self._cmd_whoami(argv[1:])
        if first == "user":
            # 管理员命令当前公共契约不支持；明确返回用法错误。
            self._err("'agentos-tui user ...' is not supported in current contract.")
            return EXIT_USAGE

        # 未知子命令：报用法错误。
        self._err(f"Unknown command or argument: {first}")
        return EXIT_USAGE

    # ------------------------------------------------------------------
    # 默认命令：恢复登录态或引导登录，然后启动主 TUI
    # ------------------------------------------------------------------

    def _cmd_default(self, argv: tuple[str, ...]) -> int:
        """默认启动流程。"""
        # 1. 解析 launcher 自有参数和 TUI 参数。
        launcher_opts, tui_argv = self.parse_launcher_args(argv)

        # 2. 构造 SessionService（会保存 --gateway-url / --api-url 到 config）。
        session = self._build_session_service(launcher_opts)

        # 3. 分析 tui_argv 决定模式。
        adapter = LauncherArgvAdapterImpl()
        analysis = adapter.analyze(tui_argv)

        # 4. 决定 LaunchMode 与 UserContext。
        if analysis.user_id is not None:
            # 显式兼容模式。
            mode = LaunchMode.EXPLICIT
            context = None
        else:
            # 托管模式：恢复或登录。
            context = self._restore_or_login(session, launcher_opts)
            mode = LaunchMode.MANAGED

        # 5. 解析主 TUI 可执行文件。
        resolver = ExecutableResolverImpl()
        primary = resolver.resolve(TuiTarget.PRIMARY)
        if primary is None:
            self._err("Primary executable (jiuwenswarm-tui) not found.")
            return EXIT_EXECUTABLE

        # 6. 提取 gateway URL（用于 SWITCH_CC 时的 WS 调用，也传给 jiuwenswarm-tui）。
        #    优先级：显式 gateway_url > websocket_url > --url from argv。
        config_store = FileConfigStore()
        cfg = config_store.load()
        gateway_url = (
            cfg.gateway_url
            or cfg.websocket_url
            or self._extract_url_from_argv(tui_argv)
        )

        # 7. 构造主 TUI argv（托管模式注入 --user-id, --token, --url）。
        primary_argv = adapter.build_primary_argv(tui_argv, mode, context, gateway_url)

        # 8. 提取显式模式的 token（用于 gateway WS 认证）。
        explicit_token = None
        if mode == LaunchMode.EXPLICIT:
            explicit_token = self._extract_token_from_argv(tui_argv)

        # 9. 启动 supervisor，进入运行循环。
        return self._run_supervisor_loop(
            primary=primary,
            primary_argv=primary_argv,
            mode=mode,
            context=context,
            session=session if mode == LaunchMode.MANAGED else None,
            tui_argv=tui_argv,
            adapter=adapter,
            no_save_login=launcher_opts.no_save_login,
            gateway_url=gateway_url,
            explicit_user_id=analysis.user_id,
            explicit_token=explicit_token,
        )

    # ------------------------------------------------------------------
    # login 子命令
    # ------------------------------------------------------------------

    def _cmd_login(self, argv: tuple[str, ...]) -> int:
        """login 子命令：在普通终端登录，不启动 TUI。"""
        launcher_opts, _ = self.parse_launcher_args(argv)
        session = self._build_session_service(launcher_opts)

        # 设置输入回调。
        session.set_credential_input(self._read_username_password)

        # 如果已有身份，明确确认是否替换。
        replace_existing = True
        if session.has_session:
            replace_existing = self._confirm_replace_login()

        context = session.login(
            replace_existing=replace_existing,
            save_login=not launcher_opts.no_save_login,
        )
        self._out(
            f"Logged in as {context.username} (user_id={_mask_user_id(context.user_id)}, role={context.role})"
        )
        return EXIT_OK

    # ------------------------------------------------------------------
    # logout 子命令
    # ------------------------------------------------------------------

    def _cmd_logout(self, argv: tuple[str, ...]) -> int:
        """logout 子命令：调用服务端 logout 并清除本地凭据。"""
        launcher_opts, _ = self.parse_launcher_args(argv)
        session = self._build_session_service(launcher_opts)
        try:
            session.logout()
            self._out("Logged out.")
            return EXIT_OK
        except errors.RemoteServiceError as exc:
            # 远端吊销未确认，但本地已退出。
            self._err(f"Local credentials cleared, but remote revocation unconfirmed: {exc}")
            return EXIT_NETWORK

    # ------------------------------------------------------------------
    # whoami 子命令
    # ------------------------------------------------------------------

    def _cmd_whoami(self, argv: tuple[str, ...]) -> int:
        """whoami 子命令：显示当前身份。"""
        launcher_opts, _ = self.parse_launcher_args(argv)
        session = self._build_session_service(launcher_opts)

        profile = session.whoami()
        self._out(
            f"user_id={_mask_user_id(profile.user_id)}\n"
            f"username={profile.username}\n"
            f"role={profile.role}\n"
            f"active={profile.is_active}"
        )
        return EXIT_OK

    # ------------------------------------------------------------------
    # 帮助
    # ------------------------------------------------------------------

    def _print_help(self) -> int:
        self._out(
            "Usage: agentos-tui [command] [options] [-- tui-args...]\n"
            "\n"
            "Commands:\n"
            "  (default)   Restore login or guide login, then start the primary TUI.\n"
            "  login       Login in normal terminal; does not start any TUI.\n"
            "  logout      Call server logout and clear local credentials.\n"
            "  whoami      Show current identity.\n"
            "\n"
            "Launcher options:\n"
            "  -h, --help              Show this help and exit.\n"
            "  -V, --version           Show version and exit.\n"
            "  --api-url <url>        IAM / User API base URL.\n"
            "  --gateway-url <url>    Gateway URL passed to JiuwenSwarm TUI as --url.\n"
            "  --no-save-login         Do not persist refresh token to secure storage.\n"
            "  --                      Separator; following args are passed to JiuwenSwarm TUI.\n"
            "\n"
            "Exit codes:\n"
            "  0  success\n"
            "  2  usage error\n"
            "  3  authentication failed\n"
            "  4  config or credential error\n"
            "  5  required executable unavailable\n"
            "  6  network or remote service error\n"
            "  70 internal error\n"
        )
        return EXIT_OK

    # ==================================================================
    # 内部辅助：参数解析与依赖构造
    # ==================================================================

    @staticmethod
    def parse_launcher_args(argv: tuple[str, ...]) -> tuple["_LauncherOpts", tuple[str, ...]]:
        """解析 launcher 自有参数与 TUI 参数的边界。

        返回 (LauncherOpts, tui_argv)。
        `--` 之后的元素全部归 tui_argv。
        """
        api_url: Optional[str] = None
        gateway_url: Optional[str] = None
        no_save_login = False
        tui_args: list[str] = []
        seen_separator = False

        i = 0
        n = len(argv)
        while i < n:
            arg = argv[i]

            if seen_separator:
                tui_args.append(arg)
                i += 1
                continue

            if arg == "--":
                seen_separator = True
                i += 1
                continue

            if arg == "--api-url":
                if i + 1 >= n:
                    raise errors.UsageError("--api-url requires a value.")
                api_url = argv[i + 1]
                i += 2
                continue

            if arg.startswith("--api-url="):
                api_url = arg[len("--api-url="):]
                if not api_url:
                    raise errors.UsageError("--api-url value is empty.")
                i += 1
                continue

            if arg == "--gateway-url":
                if i + 1 >= n:
                    raise errors.UsageError("--gateway-url requires a value.")
                gateway_url = argv[i + 1]
                i += 2
                continue

            if arg.startswith("--gateway-url="):
                gateway_url = arg[len("--gateway-url="):]
                if not gateway_url:
                    raise errors.UsageError("--gateway-url value is empty.")
                i += 1
                continue

            if arg == "--no-save-login":
                no_save_login = True
                i += 1
                continue

            # 其它参数归 JiuwenSwarm。
            tui_args.append(arg)
            i += 1

        return (
            _LauncherOpts(
                api_url=api_url,
                no_save_login=no_save_login,
                gateway_url=gateway_url,
            ),
            tuple(tui_args),
        )

    def _build_session_service(self, opts: "_LauncherOpts") -> SessionServiceImpl:
        """构造 SessionService 及其依赖。"""
        config_store = FileConfigStore()
        cfg = config_store.load()
        need_save = False

        # 如果命令行提供了 --api-url，覆盖配置中的值。
        if opts.api_url is not None:
            cfg = ClientConfig(
                api_url=opts.api_url,
                websocket_url=cfg.websocket_url,
                last_user_id=cfg.last_user_id,
                last_username=cfg.last_username,
                allow_insecure_http=cfg.allow_insecure_http,
                gateway_url=cfg.gateway_url,
            )
            need_save = True

        # 如果命令行提供了 --gateway-url，覆盖配置中的值。
        if opts.gateway_url is not None:
            cfg = ClientConfig(
                api_url=cfg.api_url,
                websocket_url=cfg.websocket_url,
                last_user_id=cfg.last_user_id,
                last_username=cfg.last_username,
                allow_insecure_http=cfg.allow_insecure_http,
                gateway_url=opts.gateway_url,
            )
            need_save = True

        if need_save:
            config_store.save(cfg)

        # 安全存储：优先 keyring，不可用时回退到文件存储（跨进程持久化）。
        try:
            cred_store = KeyringCredentialStore()
        except errors.CredentialStoreUnavailable:
            cred_store = FileCredentialStore()

        cfg = config_store.load()
        self._out(f"Config: {config_store.config_path()}")
        auth_client = RequestsAuthClient(
            allow_insecure_http=cfg.allow_insecure_http
        )

        return SessionServiceImpl(
            auth_client=auth_client,
            credential_store=cred_store,
            config_store=config_store,
        )

    # ==================================================================
    # 内部辅助：登录与恢复
    # ==================================================================

    def _restore_or_login(
        self,
        session: SessionServiceImpl,
        opts: "_LauncherOpts",
    ) -> UserContext:
        """恢复登录态；失败则引导交互登录。"""
        # 1. 尝试 restore。
        try:
            context = session.restore()
        except errors.NetworkUnavailable as exc:
            self._err(f"Cannot reach service to restore login: {exc}")
            # 询问是否继续登录；用户取消则按退出码 3 返回。
            if not self._confirm("Try interactive login instead?"):
                raise errors.AuthenticationExpired(
                    "Network unavailable and user declined login."
                )
            context = None
        except errors.RemoteServiceError as exc:
            self._err(f"Remote service error during restore: {exc}")
            if not self._confirm("Try interactive login instead?"):
                raise
            context = None

        if context is not None:
            return context

        # 2. 进入交互登录流程。
        session.set_credential_input(self._read_username_password)
        return session.login(
            replace_existing=False,
            save_login=not opts.no_save_login,
        )

    # ==================================================================
    # 内部辅助：argv 参数提取
    # ==================================================================

    @staticmethod
    def _extract_url_from_argv(tui_argv: tuple[str, ...]) -> Optional[str]:
        """从 TUI argv 中提取 --url 值。

        支持 `--url <value>` 和 `--url=<value>` 两种形式。
        """
        i = 0
        n = len(tui_argv)
        while i < n:
            arg = tui_argv[i]
            if arg.startswith("--url="):
                return arg[len("--url="):]
            if arg == "--url" and i + 1 < n:
                return tui_argv[i + 1]
            i += 1
        return None

    @staticmethod
    def _extract_token_from_argv(tui_argv: tuple[str, ...]) -> Optional[str]:
        """从 TUI argv 中提取 --token 值。

        支持 `--token <value>` 和 `--token=<value>` 两种形式。
        """
        i = 0
        n = len(tui_argv)
        while i < n:
            arg = tui_argv[i]
            if arg.startswith("--token="):
                return arg[len("--token="):]
            if arg == "--token" and i + 1 < n:
                return tui_argv[i + 1]
            i += 1
        return None

    # ==================================================================
    # 内部辅助：supervisor 运行循环
    # ==================================================================

    def _run_supervisor_loop(
        self,
        *,
        primary: ResolvedExecutable,
        primary_argv: tuple[str, ...],
        mode: LaunchMode,
        context: Optional[UserContext],
        session: Optional[SessionServiceImpl],
        tui_argv: tuple[str, ...],
        adapter: LauncherArgvAdapter,
        no_save_login: bool = False,
        gateway_url: Optional[str] = None,
        explicit_user_id: Optional[str] = None,
        explicit_token: Optional[str] = None,
    ) -> int:
        """运行 supervisor，处理 SWITCH_CC 和 REAUTH_REQUIRED。

        新设计下 SWITCH_CC 流程：
        1. 从子进程 stdout 解析 handoff JSON（content + parsed）
        2. 通过 gateway WS 调用 3rdagent.switch 获取 SSH 端点
        3. 通过 SSH 隧道连接三方 Agentos 并发送 parsed 内容
        4. SSH 会话结束后重启主 TUI
        """
        runner = SubprocessRunner()
        protocol = SupervisionProtocol()
        supervisor = TuiSupervisor(
            runner=runner,
            protocol=protocol,
            resolver=ExecutableResolverImpl(),
        )

        # base_env 是 launcher 的环境，去掉可能存在的协议变量以防旧值干扰。
        base_env = dict(os.environ)
        from .protocol import strip_protocol_env

        base_env = strip_protocol_env(base_env)
        cwd = os.getcwd()

        reauth_enabled = mode == LaunchMode.MANAGED

        # 循环保护：滚动 60 秒窗口内最多自动处理一次 REAUTH_REQUIRED。
        reauth_timestamps: list[float] = []

        # 循环保护：滚动 60 秒窗口内最多切换 5 次。
        switch_timestamps: list[float] = []

        # gateway / SSH 客户端（延迟创建）。
        gateway_client: Optional[GatewayClient] = None
        ssh_client: Optional[SshTunnelClient] = None

        # 第一次启动主 TUI。
        current_argv = primary_argv
        current_context = context

        # 上一次 /switch 的 target（如 "claude"），后续 SSH 可复用。
        last_switch_target: Optional[str] = None

        while True:
            result: SupervisedProcessResult = supervisor.run_primary(
                primary=primary,
                primary_argv=current_argv,
                reauth_enabled=reauth_enabled,
                base_env=base_env,
                cwd=cwd,
            )

            if result.action is None:
                # 普通退出码原样返回。
                return result.exit_code

            if result.action == HandoffAction.SWITCH_CC:
                # 新设计：通过 gateway WS + SSH 隧道切换到三方 Agentos。
                # 循环保护。
                now = time.monotonic()
                switch_timestamps = [
                    t for t in switch_timestamps
                    if now - t < SWITCH_LOOP_WINDOW_SECONDS
                ]
                if len(switch_timestamps) >= SWITCH_LOOP_MAX_IN_WINDOW:
                    self._err(
                        "Switch loop detected: too many switches within "
                        f"{int(SWITCH_LOOP_WINDOW_SECONDS)} seconds."
                    )
                    return EXIT_AUTH
                switch_timestamps.append(now)
                # 1. 从 stdout 解析 handoff JSON。
                if not result.stdout:
                    self._err("Handoff capture failed: TUI stdout is empty.")
                    return EXIT_INTERNAL
                try:
                    handoff = parse_handoff_stdout(result.stdout)
                except errors.HandoffParseError as exc:
                    self._err(f"Handoff parse error: {exc}")
                    return EXIT_INTERNAL

                # 更新上次 switch target；若 parsed 为空则复用上一次的值。
                if handoff.parsed:
                    last_switch_target = handoff.parsed
                switch_target = handoff.parsed or last_switch_target
                if not switch_target:
                    self._err("No switch target specified and no previous target available.")
                    return EXIT_USAGE

                # 2. 确定 gateway URL。
                if not gateway_url:
                    self._err(
                        "Gateway URL not configured; cannot switch to 3rd agent."
                    )
                    return EXIT_CONFIG

                # 3. 获取 user_id 用于 gateway WS 认证。
                #    gateway 校验逻辑：若提供 token，则校验 token 用户与 X-User-Id 一致；
                #    若不提供 token，仅用 X-User-Id 标识用户。
                #    当前 gateway 版本对 token 校验较严格（过期/格式问题会关闭连接），
                #    暂不传 token，只用 X-User-Id，与 jiuwenswarm-tui 默认行为对齐。
                ws_user_id = None
                if mode == LaunchMode.MANAGED and current_context is not None:
                    ws_user_id = current_context.username
                else:
                    ws_user_id = explicit_user_id

                # 4. 调用 gateway WS 获取 SSH 端点。
                #    生成 session_id（UUID），用于 gateway 会话追踪。
                #    不传 token：当前 gateway 版本对 token 校验较严格，
                #    仅用 X-User-Id 即可建立连接（与 jiuwenswarm-tui 默认行为一致）。
                session_id = str(uuid.uuid4())
                try:
                    if gateway_client is None:
                        gateway_client = WebSocketGatewayClient()
                    endpoint = gateway_client.switch(
                        gateway_url=gateway_url,
                        agent_type=switch_target,
                        session_id=session_id,
                        token=None,
                        user_id=ws_user_id,
                    )
                except errors.GatewayError as exc:
                    self._err(f"Gateway error: {exc}")
                    return EXIT_NETWORK
                except Exception as exc:
                    # 兜底：捕获逃逸的原始异常（如 websockets 库直接抛出的
                    # ConnectionClosed），打印完整类型信息辅助诊断。
                    import traceback
                    self._err(
                        f"Gateway call failed (unhandled): "
                        f"{type(exc).__module__}.{type(exc).__name__}: {exc}"
                    )
                    self._err(f"Traceback:\n{traceback.format_exc()}")
                    return EXIT_NETWORK

                # 5. 通过 SSH 隧道连接三方 Agentos 并发送内容。
                if ssh_client is None:
                    ssh_client = ParamikoSshTunnelClient()
                try:
                    ssh_client.connect_and_send(
                        ssh_ip=endpoint.ssh_ip,
                        ssh_port=endpoint.ssh_port,
                        content=switch_target,
                        username=ws_user_id,
                    )
                except errors.SshTunnelError as exc:
                    self._err(f"SSH tunnel error: {exc}")
                    return EXIT_NETWORK
                except Exception as exc:
                    import traceback
                    self._err(
                        f"SSH tunnel call failed (unhandled): "
                        f"{type(exc).__module__}.{type(exc).__name__}: {exc}"
                    )
                    self._err(f"Traceback:\n{traceback.format_exc()}")
                    return EXIT_NETWORK

                # SSH 会话结束；重启主 TUI，继续外层循环。
                continue

            if result.action == HandoffAction.REAUTH_REQUIRED:
                # 重新认证；只在托管模式有效。
                if mode != LaunchMode.MANAGED or session is None:
                    return result.exit_code

                # 循环保护：检查滚动 60 秒窗口。
                now = time.monotonic()
                reauth_timestamps = [
                    t for t in reauth_timestamps if now - t < REAUTH_WINDOW_SECONDS
                ]
                if len(reauth_timestamps) >= REAUTH_MAX_IN_WINDOW:
                    self._err(
                        "Reauthentication loop detected: "
                        "multiple REAUTH_REQUIRED within 60 seconds."
                    )
                    return EXIT_AUTH
                reauth_timestamps.append(now)

                # 调用 SessionService.renew()。
                try:
                    new_context = session.renew()
                except errors.AuthenticationExpired as exc:
                    self._err(f"Refresh rejected: {exc}")
                    return self._fallback_to_login_after_reauth_fail(
                        session=session,
                        no_save_login=no_save_login,
                        adapter=adapter,
                        tui_argv=tui_argv,
                        primary=primary,
                        supervisor=supervisor,
                        base_env=base_env,
                        cwd=cwd,
                        gateway_url=gateway_url,
                    )
                except (errors.NetworkUnavailable, errors.RemoteServiceError) as exc:
                    self._err(f"Network/remote error during refresh: {exc}")
                    return EXIT_NETWORK

                # 重新构造 argv。
                current_context = new_context
                current_argv = adapter.build_primary_argv(
                    tui_argv, mode, new_context, gateway_url
                )
                continue

            # 不应该到这里。
            return result.exit_code

    def _fallback_to_login_after_reauth_fail(
        self,
        *,
        session: SessionServiceImpl,
        no_save_login: bool,
        adapter: LauncherArgvAdapter,
        tui_argv: tuple[str, ...],
        primary: ResolvedExecutable,
        supervisor: TuiSupervisor,
        base_env: dict[str, str],
        cwd: str,
        gateway_url: Optional[str] = None,
    ) -> int:
        """refresh 被拒绝后进入交互登录流程。

        公共契约：refresh 被拒绝时必须清理失效凭据并在普通终端进入登录；
        用户取消或无法交互时返回退出码 3。
        """
        try:
            session.set_credential_input(self._read_username_password)
            new_context = session.login(
                replace_existing=False,
                save_login=not no_save_login,
            )
        except (KeyboardInterrupt, errors.LauncherError) as exc:
            self._err(f"Login failed: {exc}")
            return EXIT_AUTH

        # 重新构造 argv 并启动主 TUI。
        new_argv = adapter.build_primary_argv(
            tui_argv, LaunchMode.MANAGED, new_context, gateway_url
        )
        result = supervisor.run_primary(
            primary=primary,
            primary_argv=new_argv,
            reauth_enabled=True,
            base_env=base_env,
            cwd=cwd,
        )
        return result.exit_code

    # ==================================================================
    # 内部辅助：交互输入
    # ==================================================================

    def _read_username_password(self) -> tuple[str, str]:
        """读取用户名和密码（关闭回显）。"""
        self._out("Login to AgentOS:")
        username = input("Username: ").strip()
        if not username:
            raise errors.UsageError("Username is empty.")
        try:
            password = getpass.getpass("Password: ")
        except (EOFError, KeyboardInterrupt) as exc:
            raise errors.AuthenticationExpired("Login cancelled by user.") from exc
        if not password:
            raise errors.UsageError("Password is empty.")
        return username, password

    def _confirm_replace_login(self) -> bool:
        """已有身份时确认是否替换。"""
        return self._confirm("Already logged in. Replace existing login?")

    @staticmethod
    def _confirm(prompt: str) -> bool:
        """通用 yes/no 确认。"""
        try:
            answer = input(f"{prompt} [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return answer in ("y", "yes")

    # ==================================================================
    # 输出辅助
    # ==================================================================

    def _out(self, message: str) -> None:
        self._out_logger.info(message)

    def _err(self, message: str) -> None:
        self._err_logger.error(message)


# ============================================================================
# 辅助类型与函数
# ============================================================================


class _LauncherOpts:
    """launcher 自有参数解析结果。"""

    __slots__ = ("api_url", "no_save_login", "gateway_url")

    def __init__(
        self,
        *,
        api_url: Optional[str],
        no_save_login: bool,
        gateway_url: Optional[str] = None,
    ) -> None:
        self.api_url = api_url
        self.no_save_login = no_save_login
        self.gateway_url = gateway_url


def _mask_user_id(user_id: str) -> str:
    """脱敏 user_id。

    公共契约要求默认不记录完整 user_id；确需关联时使用不可逆脱敏标识。
    这里保留前 8 位 + 后 4 位，中间替换为 ...。
    """
    if len(user_id) <= 12:
        return user_id[:4] + "..."
    return f"{user_id[:8]}...{user_id[-4:]}"
