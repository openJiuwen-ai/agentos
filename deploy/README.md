# agentos 统一部署脚本

## 简介

本目录是 agentos 的统一部署入口，采用**可插拔架构**编排各组件的安装与部署。

当前已注册模块：

| 模块 | 说明 | 部署/安装内容 |
| --- | --- | --- |
| `jiuwenbox` | 沙箱服务 | 在 `--hosts` 每台机器同构启动 jiuwenbox-server（随 jiuwenswarm whl 安装） |
| `yuanrong` | openyuanrong 集群 | 分布式进程模式集群（master + agent） |
| `jiuwenswarm` | jiuwenswarm 函数 + gateway | 函数注册 + gateway 进程（whl 包已包含 gateway） |

## 目录结构

```
deploy/
├── agentos.sh                # agentos 部署总脚本（不含模块特有逻辑）
├── README.md                 # 本文档
├── jiuwenbox/
│   ├── module.sh             # jiuwenbox 钩子（含 --hosts 编排）
│   ├── jiuwenbox_deploy.sh   # up/down/restart（含 --hosts 编排）
│   └── default-policy.yaml   # policy 模板（含 extensions 占位符）
├── yuanrong/
│   ├── module.sh             # yuanrong 钩子函数
│   └── yuanrong_deploy.sh    # yuanrong 原始部署脚本
└── jiuwenswarm/
    ├── module.sh             # jiuwenswarm 钩子函数
    └── .env.custom           # jiuwenswarm 配置文件
```

## 架构设计

核心机制：**模块注册 + 钩子函数 + 调度引擎**。

1. **模块注册**：`agentos.sh` 顶部的 `MODULES` 数组声明所有模块及其部署顺序。
2. **钩子约定**：每个模块在 `deploy/<module>/module.sh` 中实现 4 个钩子函数：
   - `<module>_up` — 启动/部署
   - `<module>_down` — 停止/卸载
   - `<module>_install` — 安装 whl 包（本机）
   - `<module>_uninstall` — 卸载 whl 包（本机）
3. **调度引擎**：`run_hooks` 函数遍历模块调用对应钩子。
   - `up` / `install`：按 `MODULES` 声明顺序
   - `down` / `uninstall`：自动逆序
4. **模块加载**：`load_modules` 在启动时 `source` 所有 `module.sh`，使钩子函数在当前 shell 中可用。

## 使用方法

### 前置要求

- 部署机器到所有目标主机需配置 SSH 免密登录
- 目标主机需预装指定版本的 Python（默认 3.11）
- 部署机器需预装 jiuwenbox 所需的命令：`bwrap`、`ip`、`iptables`（或 `iptables-nft` / `iptables-legacy`）
- `up` / `restart` 不安装 whl 包，请先在各目标主机执行 `install`

### 安装包获取

下载或自行构建 `AgentOS-Server.tgz` 安装包并解压，执行 `deploy` 目录中的 `agentos.sh` 脚本。

- 下载地址示例：
  - x86：`https://openjiuwen-ci.obs.cn-north-4.myhuaweicloud.com/agent-os/package/release/dist/20260715/x86_64/AgentOS-Server.tgz`
  - arm：`https://openjiuwen-ci.obs.cn-north-4.myhuaweicloud.com/agent-os/package/release/dist/20260715/aarch64/AgentOS-Server.tgz`
- 自行构建：见 [agentos/README.md](../README.md)

### 命令

#### 单机部署

```bash
# 本机安装全部 whl 包
bash agentos.sh install

# 一键部署全部组件到本机
bash agentos.sh up

# 停止并卸载本机的全部组件
bash agentos.sh down

# 重启本机的全部组件（先 down 再 up）
bash agentos.sh restart

# 卸载本机全部 whl 包
bash agentos.sh uninstall
```

#### 多机部署（TODO）

```bash
# 一键部署全部组件（多机，第一个 IP 为 master，其余为 agent）
bash agentos.sh up --hosts 192.168.1.1,192.168.1.2,192.168.1.3

# 停止并卸载全部组件
bash agentos.sh down --hosts 192.168.1.1,192.168.1.2

# 重启全部组件（先 down 再 up）
bash agentos.sh restart --hosts 192.168.1.1
```

### 参数说明

| 参数 | 说明 |
| --- | --- |
| `up` | 按声明顺序部署全部组件 |
| `down` | 逆序停止并卸载全部组件 |
| `restart` | 重启全部组件（先 down 再 up） |
| `install` | 在本机安装全部组件的 whl 包（不启动服务） |
| `uninstall` | 在本机卸载全部组件的 whl 包 |
| `--hosts HOSTS` | 目标主机 IP 列表，逗号分隔。yuanrong：第一个为 master、其余为 agent；jiuwenbox：每台各启一份。不指定时默认本机 IP |
| `-h, --help` | 显示帮助信息 |

### 配置

#### jiuwenbox

- 配置文件：`deploy/jiuwenbox/default-policy.yaml`（`__JIUWENSWARM_EXTENSIONS_DIR__` 在各机 start 时按该机 `pip show jiuwenswarm` 替换）
- `module.sh` 为薄封装；`--hosts` 编排与启停逻辑在 `jiuwenbox_deploy.sh`
- `--hosts` 时在列表中**每一台**启动一份 jiuwenbox（无 master/agent 差异）；远端 scp 后执行同一套 `up`/`down`（对端默认本机 IP，只走本机启停）
- 已有实例时只报错、不自动清理（对齐 yuanrong）；需先 `down` 再 `up`
- 前置：各目标机已安装 jiuwenswarm（含 `jiuwenbox-server`），控制机到目标机 root SSH 免密

#### yuanrong

通过环境变量传入，常用变量：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `YR_PYTHON_VERSION` | Python 版本 | `3.11` |
| `YR_VERSION` | openyuanrong release 版本号 | `0.9.0` |
| `YR_PKG_BASE` | whl 包来源（远程 URL 基址或本地目录路径） | `install` 时默认指向 agentos 根目录 |

详见 `yuanrong_deploy.sh -h`。

#### jiuwenswarm

配置文件：`deploy/jiuwenswarm/.env.custom`（基于 submodule 中的 `.env.example` 修改）。主要配置项：

| 变量 | 说明 |
| --- | --- |
| `CLUSTER_HOSTS` | 目标主机 IP 列表（也可通过 `--hosts` 参数指定，命令行优先级更高） |
| `JIUWENSWARM_PACKAGE_URL` | jiuwenswarm 安装包 URL（up 时若远程主机未安装 jiuwenswarm 则用此 URL pip 安装） |
| `MODEL_PROVIDER` / `MODEL_NAME` / `API_BASE` / `API_KEY` | 大模型接口配置 |
| `EMBED_MODEL` / `EMBED_API_BASE` / `EMBED_API_KEY` | 向量模型接口配置 |

#### whl 包来源

`install` 时统一从 agentos 根目录（`deploy` 的同级目录）获取 whl 包：

- **openyuanrong**：`YR_PKG_BASE` 默认指向 agentos 根目录，yuanrong 脚本按版本/arch 自动拼接 whl 文件名
- **jiuwenswarm**：匹配 `jiuwenswarm-*-py3-none-any.whl`（如 `jiuwenswarm-0.2.3-py3-none-any.whl`，已包含 gateway）

可通过 `YR_PKG_BASE=/other/path bash agentos.sh install` 覆盖 yuanrong 的 whl 目录。

---

## 开发者指南：新增模块

新增一个组件模块只需**两步**，无需修改 `agentos.sh` 中的任何调度逻辑。

### 第 1 步：创建模块目录和 `module.sh`

在 `deploy/` 下新建 `<module>/` 目录，放入 `module.sh`，实现 4 个钩子函数：

```bash
# deploy/mymodule/module.sh

# 部署/启动（远程或本机）
mymodule_up() {
    # 调用你的部署脚本，sub_args 已由调度器构造好（包含 --hosts 等参数）
    bash "${SCRIPT_DIR}/mymodule/deploy_mymodule.sh" up "$@"
}

# 停止/卸载（远程或本机）
mymodule_down() {
    bash "${SCRIPT_DIR}/mymodule/deploy_mymodule.sh" down "$@"
}

# 安装 whl 包（本机）
mymodule_install() {
    local found_whl
    found_whl=$(ls "${AGENTOS_ROOT}"/mymodule-*.whl 2>/dev/null || true)
    if [ -n "${found_whl}" ]; then
        bash -c "python${YR_PYTHON_VERSION} -m pip install '${found_whl}' --quiet"
        success "mymodule installed"
    else
        warning "mymodule whl not found, skipping"
    fi
}

# 卸载 whl 包（本机）
mymodule_uninstall() {
    bash -c "python${YR_PYTHON_VERSION} -m pip uninstall -y mymodule 2>/dev/null" \
        && success "mymodule uninstalled" \
        || warning "mymodule not installed or failed to uninstall"
}
```

### 第 2 步：注册到 `MODULES` 数组

编辑 `agentos.sh` 顶部的 `MODULES` 数组，按部署顺序添加模块名：

```bash
MODULES=("yuanrong" "jiuwenswarm" "mymodule")
```

### 完成

此后 `bash agentos.sh up` 会自动按 `yuanrong → jiuwenswarm → mymodule` 顺序部署，`bash agentos.sh down` 会逆序卸载，`install` / `uninstall` 同理。

### 钩子函数说明

| 钩子 | 调用时机 | 参数 | 典型实现 |
| --- | --- | --- | --- |
| `<module>_up` | `up` / `restart` 时，按声明顺序调用 | `--hosts ...` 等透传参数 | 调用模块部署脚本启动服务 |
| `<module>_down` | `down` / `restart` 时，逆序调用 | `--hosts ...` 等透传参数 | 调用模块部署脚本停止服务 |
| `<module>_install` | `install` 时，按声明顺序调用 | `--hosts ...` 等透传参数（通常 install 不需要） | 本机 pip 安装 whl 包 |
| `<module>_uninstall` | `uninstall` 时，逆序调用 | `--hosts ...` 等透传参数（通常 uninstall 不需要） | 本机 pip 卸载 whl 包 |

### 可用的全局变量

`module.sh` 中可直接引用以下变量（由 `agentos.sh` 在 `source` 前定义）：

| 变量 | 说明 |
| --- | --- |
| `SCRIPT_DIR` | `deploy/` 目录的绝对路径 |
| `AGENTOS_ROOT` | agentos 根目录（`deploy` 的同级目录）的绝对路径 |
| `MODULES` | 已注册模块数组 |
| `YR_PYTHON_VERSION` | Python 版本（默认 `3.11`） |
| `CLUSTER_HOSTS` | `--hosts` 参数解析出的主机列表 |
| `info` / `success` / `warning` / `error` | 日志函数 |

### 可选钩子

钩子函数是可选的。若某模块未实现某个钩子（如纯部署型模块不需要 `install`），调度引擎会打印 warning 并跳过，不会报错中断。

### 命名规范

- 模块名使用小写字母 + 数字 + 连字符（如 `mymodule`、`skill-store`）
- 钩子函数名必须为 `<module名>_<hook>`，其中 `<hook>` 为 `up` / `down` / `install` / `uninstall`
- `module.sh` 中定义的内部函数建议加 `_` 前缀（如 `_mymodule_helper`）避免命名冲突
