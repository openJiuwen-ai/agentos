# AgentOS TUI Launcher

AgentOS TUI 启动器，负责用户登录、登录态恢复、`/switch-claude` 三类 Agent 切换。

---

## 前置条件

使用 launcher 前，需确保以下服务和组件已就绪。

### 1. 管理面（Control Panel）服务

管理面提供 IAM 登录认证和用户管理 API，需先部署并启动。

部署参考：<https://gitcode.com/openJiuwen/agent-os/tree/main/control-panel/deploy>

部署后确认 API 可访问（示例地址 `http://<host>:8090`）。

### 2. Gateway 服务

Gateway 提供 WebSocket 连接，是 TUI 与后端通信的桥梁，同时也是 `/switch-claude` 三类 Agent 切换的入口。

部署后确认 WebSocket 地址可用（示例地址 `ws://<host>:19001/tui`）。

### 3. JiuwenSwarm-tui 安装

从 [Releases 页面](https://gitcode.com/openJiuwen/jiuwenswarm/releases) 下载最新 `jiuwenswarm-tui` 包并安装：

```bash
pip install jiuwenswarm-tui*.whl
```

安装后 `jiuwenswarm-tui` 命令会出现在 PATH 中。

---

## 环境变量（先设置，再启动）

| 变量 | 说明 |
|------|------|
| `AGENTOS_TUI_PRIMARY_PATH` | `jiuwenswarm-tui` 可执行文件路径（推荐设置） |
| `AGENTOS_TUI_CONFIG_DIR` | 覆盖配置目录（可选） |
| `AGENTOS_TUI_CC_PATH` | cc-tui 可执行文件路径（可选） |

### 各平台设置示例

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

---

## 安装 launcher

```bash
pip install agentos_tui_launcher-*.whl
```

---

## 首次启动

直接带参数运行，会自动弹出登录提示，并把配置写入文件：

```bash
agentos-tui login --api-url http://<your-server>:8090 --gateway-url ws://<your-server>:19001/tui
```

输入用户名密码，`jiuwenswarm-tui` 自动启动。

---

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
| `last_user_id` | 否 | 自动写入，上次登录的用户 ID |
| `last_username` | 否 | 自动写入，上次登录的用户名 |

---

## 之后使用

首次启动后配置已自动写入，路径会在启动时打印。之后可直接运行：

```bash
agentos-tui
```
## `/switch-claude` 切换流程

1. 登录后，输入`agentos-tui`，`jiuwenswarm-tui` 会自动启动。
2. 在 TUI 中，输入 `/switch-claude` 指令。
3.  launcher 会通过 Gateway 调用 `/switch-claude` 接口，获取 SSH 端点。
4.  launcher 会建立 SSH 隧道，将本地端口映射到远程服务器。
5.  在本地，使用 SSH 客户端（如 `ssh` 命令）连接到本地端口，即可交互式操作 Claude Agent。

## 其他命令参考

```bash
agentos-tui logout                 # 登出并清除凭据
agentos-tui whoami                 # 查看当前登录身份
agentos-tui --help                 # 帮助
```

### launcher 自有参数

| 参数 | 说明 |
|------|------|
| `--api-url <url>` | IAM API 地址（会写入配置） |
| `--gateway-url <url>` | Gateway WebSocket 地址（会写入配置） |
| `--no-save-login` | 本次登录不保存 refresh token |

### 显式模式

跳过登录流程，直接启动 TUI。适合无 IAM 服务的场景。

> `--url` 即配置中的 `gateway_url`（Gateway WebSocket 地址），`--user-id` 填配置中的 `last_username`（**用户名**，不是 UUID）。

```bash
# 显式指定用户名
agentos-tui --url ws://host:19001/tui --user-id xxx
```

---

## 构建

```bash
cd tui-launcher
python -m pip wheel --no-deps -w dist/ .
```

产出：`dist/agentos_tui_launcher-0.1.0-py3-none-any.whl`
