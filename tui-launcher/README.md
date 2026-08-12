# AgentOS TUI Launcher

AgentOS TUI 启动器，负责用户登录、登录态恢复、`/switch-claude` 三类 Agent 切换。

---

## 0 前置条件

使用 launcher 前，需确保以下服务和组件已就绪。

### (1). 管理面（Control Panel）服务

管理面提供 IAM 登录认证和用户管理 API，需先部署并启动。

部署参考：<https://gitcode.com/openJiuwen/agent-os/tree/main/control-panel/deploy>

部署后确认 API 可访问（示例地址 `http://<host>:8090`）。

### (2). Gateway 服务

Gateway 提供 WebSocket 连接，是 TUI 与后端通信的桥梁，同时也是 `/switch-claude` 三类 Agent 切换的入口。

部署后确认 WebSocket 地址可用（示例地址 `ws://<host>:19001/tui`）。

### (3). JiuwenSwarm-tui 安装

从 [Releases 页面](https://gitcode.com/openJiuwen/jiuwenswarm/releases) 下载最新 `jiuwenswarm-tui` 包并安装：

```bash
pip install jiuwenswarm-tui*.whl
```

安装后 `jiuwenswarm-tui` 命令会出现在 PATH 中。

---

## 1 安装 launcher

下载地址：<https://openjiuwen-ci.obs.cn-north-4.myhuaweicloud.com/agent-os/package/index.html>（在 `AgentOS-Client.tgz` 中）

```bash
pip install agentos_tui_launcher-*.whl
```

---

## 2 登录

直接运行，会自动弹出登录提示，并把配置写入文件：

```bash
agentos-tui --api-url http://<your-server>:8090 --gateway-url ws://<your-server>:19001/tui --allow-insecure-http true
```

各参数说明：

| 参数 | 说明 |
|------|------|
| `--api-url <url>` | IAM API 地址（会写入配置） |
| `--gateway-url <url>` | Gateway WebSocket 地址（会写入配置） |
| `--allow-insecure-http[=true\|false]` | 允许 HTTP 连接；不加值等效于 `true` |
| `--no-allow-insecure-http` | 禁止 HTTP 连接（覆盖 `--allow-insecure-http`） |
| `--no-save-login` | 本次登录不保存 refresh token |

输入用户名密码后，登录成功。

---

## 3 使用

登录后配置已自动写入，路径会在启动时打印。之后可直接运行：

```bash
agentos-tui
```

## 4 `/switch-claude` 切换流程

在 TUI 中输入 `/switch-claude` 指令，launcher 会自动建立 SSH 隧道连接到对应的 Agent 服务器。退出三方 Agent 时，输入 `exit` 或按 `Ctrl+D` 断开 SSH 连接，即可返回 TUI。

---

## 5 其他命令参考

```bash
agentos-tui logout                 # 登出并清除凭据
agentos-tui whoami                 # 查看当前登录身份
agentos-tui --help                 # 帮助
```

---

## 6 显式模式

跳过登录流程，直接启动 TUI，由用户直接提供 `--user-id` 和 `--token`。

> `--url` 即配置中的 `gateway_url`（Gateway WebSocket 地址），`--user-id` 填配置中的 `last_username`（**用户名**，不是 UUID），`--token` 为 access token，可通过 IAM 登录 API 获取。

```bash
# 先调用 IAM 登录 API 获取 access token
# 示例（使用 curl）：
# curl -X POST http://<host>:8090/api/v1/auth/login \
#   -H "Content-Type: application/json" \
#   -d '{"username": "xxx", "password": "xxx"}'
# 返回结果中的 access_token 即为 --token 的值。

# 然后启动 TUI
agentos-tui --url ws://host:19001/tui --user-id <username> --token <access_token>
```

---

## 7 日志文件

launcher 运行日志自动写入 `~/.agentos-tui/logs/launcher.log`，轮转策略：单文件最大 10MB，保留最近 5 个备份。

| 平台 | 日志路径 |
|------|---------|
| Windows | `%USERPROFILE%\.agentos-tui\logs\launcher.log` |
| Linux | `~/.agentos-tui/logs/launcher.log` |
| macOS | `~/.agentos-tui/logs/launcher.log` |

---

## 8 配置文件

如需修改配置，编辑对应平台的文件：

| 平台 | 路径 |
|------|------|
| Windows | `%APPDATA%\AgentOS\tui-launcher\config.json` |
| Linux | `~/.config/agentos/tui-launcher/config.json` |
| macOS | `~/Library/Application Support/AgentOS/tui-launcher/config.json` |

`AGENTOS_TUI_CONFIG_DIR` 环境变量可覆盖默认路径。

配置文件内容示例：

```json
{
  "api_url": "http://<your-server>:8090",
  "gateway_url": "ws://<your-server>:19001/tui",
  "allow_insecure_http": true
}
```

| 字段 | 必填 | 说明 |
|------|:--:|------|
| `api_url` | 是 | IAM / User API 地址，对应管理面服务 |
| `gateway_url` | 是 | Gateway WebSocket 地址，同时作为 TUI 的 `--url` |
| `allow_insecure_http` | 是 | API 用 HTTP 时必须设为 `true` |
| `last_user_id` | 否 | 自动写入，最近使用的用户 ID，用于定位 refresh token 和登录提示 |
| `last_username` | 否 | 自动写入，最近使用的用户名，用于定位 refresh token 和登录提示 |

---

## 9 构建

```bash
cd tui-launcher
python -m pip wheel --no-deps -w dist/ .
```

产出：`dist/agentos_tui_launcher-0.1.0-py3-none-any.whl`

---

## 10 常见问题排查

### 找不到可执行文件

launcher 启动时会自动在 `PATH` 中查找 `jiuwenswarm-tui`，一般无需额外配置。如果遇到找不到可执行文件等报错，可通过以下环境变量手动指定路径：

| 变量 | 说明 |
|------|------|
| `AGENTOS_TUI_PRIMARY_PATH` | `jiuwenswarm-tui` 可执行文件路径 |
| `AGENTOS_TUI_CONFIG_DIR` | 覆盖配置目录（可选） |
| `AGENTOS_TUI_CC_PATH` | cc-tui 可执行文件路径（可选） |

**各平台设置示例：**

**Linux / macOS:**

```bash
export AGENTOS_TUI_PRIMARY_PATH=$(which jiuwenswarm-tui)
```

**Windows (PowerShell):**

```powershell
$env:AGENTOS_TUI_PRIMARY_PATH = (Get-Command jiuwenswarm-tui).Source
```

**Windows (CMD):**

```cmd
for /f "tokens=*" %i in ('where jiuwenswarm-tui') do set AGENTOS_TUI_PRIMARY_PATH=%i
```
