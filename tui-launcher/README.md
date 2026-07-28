# AgentOS TUI Launcher

AgentOS 顶层 TUI 启动器，负责用户登录、登录态恢复、`/switch-claude` 切换与运行中 access token 重新认证。

## 前置条件

### 1. 设置主 TUI 可执行文件路径

launcher 通过环境变量 `AGENTOS_TUI_PRIMARY_PATH` 定位 JiuwenSwarm TUI 入口脚本，例如：

```bash
export AGENTOS_TUI_PRIMARY_PATH=/path/to/jiuwenswarm-tui
```

如果不设置，launcher 会按以下顺序查找：
1. 环境变量 `AGENTOS_TUI_PRIMARY_PATH`
2. PATH 上的 `jiuwenswarm-tui` 命令

若找不到，启动失败（退出码 5）。

### 2. 配置文件

配置文件位于（自动创建，无需手动创建）：

| 平台 | 路径 |
|------|------|
| Linux | `~/.config/agentos/tui-launcher/config.json` |
| macOS | `~/Library/Application Support/AgentOS/tui-launcher/config.json` |
| Windows | `%APPDATA%\AgentOS\tui-launcher\config.json` |

可通过环境变量 `AGENTOS_TUI_CONFIG_DIR` 覆盖配置目录。

第一次 `agentos-tui login --api-url <url>` 后，`login` 命令会自动写入配置文件。也可以手动编辑：

```json
{
  "api_url": "http://<host>:<port>",
  "gateway_url": "ws://<host>:<port>/tui",
  "last_user_id": "fa3b97a6-c538-4d85-a903-f0ad486338d4",
  "last_username": "admin",
  "allow_insecure_http": true
}
```

字段说明：

| 字段 | 说明 |
|------|------|
| `api_url` | IAM / User API 基础地址，如 `http://localhost:8090` |
| `gateway_url` | Gateway WebSocket 地址，用于 `/switch-claude` 切换时调用 `3rdagent.switch` |
| `last_user_id` | 最近登录用户 ID，用于定位安全存储中的 refresh token |
| `last_username` | 最近登录用户名，用于登录提示 |
| `allow_insecure_http` | **重要**：如果 `api_url` 使用 HTTP（非 HTTPS），必须设为 `true`，否则 launcher 拒绝连接 |

## 快速开始

```bash
# 安装（开发模式）
pip install -e .[dev]

# 第一步：登录（会自动写入配置文件）
agentos-tui login --api-url http://<host>:<port>

# 如果 API 地址是 HTTP，确保配置文件中 allow_insecure_http 为 true
# 可手动编辑 ~/.config/agentos/tui-launcher/config.json 或通过 login 命令首次登录后自动生成

# 第二步：启动主 TUI（需先设置 AGENTOS_TUI_PRIMARY_PATH）
export AGENTOS_TUI_PRIMARY_PATH=/path/to/jiuwenswarm-tui
agentos-tui

# 子命令
agentos-tui login              # 在普通终端登录，不启动 TUI
agentos-tui logout             # 调用服务端 logout 并清除本地凭据
agentos-tui whoami             # 显示当前身份

# 兼容显式启动方式（跳过 login，直接传入 user-id 和 token）
agentos-tui --url ws://<host>:<port>/tui \
  --user-id <uuid> --token <access-token>

# 使用 -- 把后续参数原样传给 JiuwenSwarm
agentos-tui --api-url https://<host> -- \
  --url wss://<host>/tui --session <session-id>
```

## 构建 wheel 包

```bash
# 方式一：通过项目构建脚本（与 jiuwenswarm_tui 一同打包到 AgentOS-Client.tgz）
cd /path/to/agentos
bash build/build.sh

# 方式二：单独构建
cd tui-launcher
python -m pip wheel --no-deps -w dist/ .
```

构建产物为 `agentos_tui_launcher-0.1.0-py3-none-any.whl`。

## 模块说明

| 模块 | 职责 |
|------|------|
| `__main__.py` | `python -m agentos_tui_launcher` 入口 |
| `cli.py` | `agentos-tui` 入口、参数分流与流程编排 |
| `config.py` | 非敏感配置（服务地址、最近用户名、`allow_insecure_http` 等）读写 |
| `auth_client.py` | IAM HTTP 客户端：登录 / 刷新 / 登出 / users/me |
| `credential_store.py` | refresh token 的安全存储抽象（keyring / 文件回退） |
| `user_context.py` | 不可变用户上下文与 `SessionService` |
| `argv_adapter.py` | 构造 JiuwenSwarm argv，处理 `--user-id` 共享边界 |
| `resolver.py` | 白名单解析 `jiuwenswarm-tui` / `cc-tui` 可执行文件 |
| `protocol.py` | 父子进程监督协议：动作码 88 / 89 / 90 与环境变量 |
| `supervisor.py` | 前台子进程监督、信号转发、退出码分类 |
| `gateway_client.py` | Gateway WebSocket 客户端，用于 handoff 切换 |
| `handoff.py` | 三方 Agent 切换（handoff）逻辑 |
| `ssh_tunnel.py` | SSH 隧道客户端，连接远程三方 Agentos |
| `errors.py` | 稳定的错误类别定义 |

## 环境变量

| 变量 | 说明 |
|------|------|
| `AGENTOS_TUI_PRIMARY_PATH` | 主 TUI（jiuwenswarm-tui）可执行文件路径，一般为必设 |
| `AGENTOS_TUI_CC_PATH` | cc-tui 可执行文件路径（可选） |
| `AGENTOS_TUI_CONFIG_DIR` | 覆盖默认配置目录（可选） |
| `AGENTOS_TUI_SUPERVISED` | launcher 启动子进程时自动注入，标记子进程处于监督模式 |
| `AGENTOS_TUI_SWITCH_CC_EXIT_CODE` | 覆盖 SWITCH_CC 动作码（默认 88） |
| `AGENTOS_TUI_REAUTH_EXIT_CODE` | 覆盖 REAUTH_REQUIRED 动作码（默认 89） |
| `AGENTOS_CC_TUI_RETURN_EXIT_CODE` | 覆盖 cc-tui 切回动作码（默认 90） |

## 退出码

| 退出码 | 含义 |
|--------|------|
| 0  | launcher 自有命令成功 |
| 2  | CLI 用法或参数契约错误 |
| 3  | 无法建立认证身份 |
| 4  | 配置或安全凭据错误 |
| 5  | 必需可执行文件或 handoff 目标不可用 |
| 6  | 网络或远端服务错误 |
| 70 | 未分类内部错误 |

子进程（JiuwenSwarm / cc-tui）的普通退出码原样透传。以下动作码仅作为子进程到 launcher 的内部协议约定，不会作为 launcher 的最终退出码返回。默认值可通过环境变量覆盖（见上方环境变量表）：

| 动作码 | 默认值 | 含义 |
|--------|--------|------|
| SWITCH_CC | 88 | 主 TUI 请求切换到三方 Agent TUI |
| REAUTH_REQUIRED | 89 | 主 TUI 请求 launcher 刷新 access token 后重启 |
| RETURN_TO_PRIMARY | 90 | cc-tui 请求切回主 TUI |