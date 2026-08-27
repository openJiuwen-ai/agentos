# agentos 统一部署脚本

## 简介

本目录是 agentos 的统一部署入口，采用**可插拔架构**编排各组件的安装与部署。

当前已注册模块（按部署顺序）：

| 模块 | 说明 | 部署/安装内容 |
| --- | --- | --- |
| `moosefs` | 分布式共享存储 | MooseFS 集群（master + chunkserver + client），单机自动跳过 |
| `jiuwenbox` | 沙箱服务 | 每台机器同构启动 jiuwenbox-server（随 jiuwenswarm whl 安装） |
| `yuanrong` | openyuanrong 集群 | 分布式进程模式集群（master + agent） |
| `agent-gateway` | A2X 注册中心 | a2x-registry 后端（sqlite 存储），优先 systemd 托管，抢占 ingress VIP 的节点启动 |
| `jiuwenswarm` | jiuwenswarm gateway + web | gateway 进程 + web 前端（whl 包已包含 gateway） |

## 目录结构

```
deploy/
├── agentos.sh                # agentos 部署总脚本（不含模块特有逻辑）
├── etcd.sh                   # etcd 独立启停脚本（init/deinit 委托给它）
├── check-ingress-master.sh   # ingress VIP 持有检查（agent-gateway systemd ExecStartPre）
├── config.yaml               # 集群拓扑配置（etcd_nodes/master_nodes/ingress_virtual_ip）
├── README.md                 # 本文档
├── moosefs/
│   ├── module.sh             # moosefs 钩子函数
│   ├── moosefs_deploy.sh     # moosefs 部署脚本（install/up/down/uninstall）
│   ├── moosefs.conf          # moosefs 配置文件
│   └── README.md             # moosefs RPM 依赖说明
├── jiuwenbox/
│   ├── module.sh             # jiuwenbox 钩子
│   ├── jiuwenbox_deploy.sh   # up/down/restart
│   └── default-policy.yaml   # policy 模板（含 extensions 占位符）
├── yuanrong/
│   ├── module.sh             # yuanrong 钩子函数
│   └── yuanrong_deploy.sh    # yuanrong 原始部署脚本
├── agent-gateway/
│   └── module.sh             # agent-gateway 钩子（A2X 注册中心，systemd/nohup 双模式）
├── jiuwenswarm/
│   ├── module.sh             # jiuwenswarm 钩子函数
│   └── .env.custom           # jiuwenswarm 配置文件
└── scripts/
    └── config.py             # 集群配置解析与角色推导工具
```

## 架构设计

核心机制：**模块注册 + 钩子函数 + 调度引擎**。

1. **模块注册**：`agentos.sh` 顶部的 `MODULES` 数组声明所有模块及其部署顺序：
   `MODULES=("moosefs" "jiuwenbox" "yuanrong" "agent-gateway" "jiuwenswarm")`
2. **钩子约定**：每个模块在 `deploy/<module>/module.sh` 中实现 5 个钩子函数：
   - `<module>_up` — 启动/部署
   - `<module>_down` — 停止/卸载
   - `<module>_install` — 安装 whl 包（本机）
   - `<module>_uninstall` — 卸载 whl 包（本机）
   - `<module>_status` — 只读状态探测（可选，未实现时占位 "not supported"）
3. **调度引擎**：`run_hooks` 函数遍历模块调用对应钩子。
   - `up` / `install`：按 `MODULES` 声明顺序
   - `down` / `uninstall`：自动逆序
4. **模块加载**：`load_modules` 在启动时 `source` 所有 `module.sh`，使钩子函数在当前 shell 中可用。
5. **etcd 委托**：etcd 作为全集群前置依赖，独立于 `up/down`，由 `etcd.sh` 单独管理（`init`/`deinit` 委托）。

### 生命周期（三对互逆操作，嵌套如括号）

```
install  ↔  uninstall     装/卸 whl（最外层）
  init   ↔  deinit        bootstrap / 拆 etcd（中层，一次性）
    up   ↔  down          起/停应用服务（最内层，可反复）
```

拆除顺序天然逆序：`down → deinit → uninstall`。

## 使用方法

### 前置要求

- **操作系统**：基于 openEuler 22.03-LTS-SP1/SP4 或 24.03-LTS-SP1/SP4（x86_64 和 aarch64），需支持 systemd
- **Python**：目标主机需预装指定版本的 Python（默认 3.11）
- **systemd**：etcd 和 agent-gateway 强依赖 systemd（`systemctl` 可用且 `/run/systemd/system` 存在）；moosefs 和 jiuwenswarm 自动检测
- **SSH 免密**：部署机器到所有目标主机需配置 SSH 免密登录（root 用户）
- **系统命令**：部署机器需预装 jiuwenbox 所需的命令：`bwrap`、`ip`、`iptables`（或 `iptables-nft` / `iptables-legacy`）；agent-gateway 需 `curl`
- **集群配置**：`deploy/config.yaml` 需按实际拓扑配置 `etcd_nodes`、`master_nodes`、`ingress_virtual_ip`（单机开发模式默认全为 `127.0.0.1`）
- **MooseFS RPM**：MooseFS RPM 包（moosefs-master、moosefs-chunkserver、moosefs-client）和 fuse3 依赖需由上游预装，详见 [moosefs/README.md](moosefs/README.md)

### 安装包获取

下载或自行构建 `AgentOS-Server.tgz` 安装包并解压，执行 `deploy` 目录中的 `agentos.sh` 脚本。

- 下载地址示例：
  - x86：`https://openjiuwen-ci.obs.cn-north-4.myhuaweicloud.com/agent-os/package/release/dist/20260715/x86_64/AgentOS-Server.tgz`
  - arm：`https://openjiuwen-ci.obs.cn-north-4.myhuaweicloud.com/agent-os/package/release/dist/20260715/aarch64/AgentOS-Server.tgz`
- 自行构建：见 [agentos/README.md](../README.md)

### 集群配置

安装部署前需编辑 `deploy/config.yaml` 配置集群拓扑：

```yaml
cluster:
  # etcd 集群节点（奇数节点保证 raft 共识）
  etcd_nodes:
    - "127.0.0.1"

  # master 节点（主备）
  master_nodes:
    - "127.0.0.1"

  # 统一入口虚拟 IP（抢占到 VIP 的节点部署 gateway/registry/web-server）
  ingress_virtual_ip: "127.0.0.1"
```

| 字段 | 说明 |
| --- | --- |
| `etcd_nodes` | etcd 集群节点 IP 列表（单机 1 节点 / 多机 HA 3 节点，奇数保证 raft 共识） |
| `master_nodes` | master 节点列表（单机 1 节点 / 多机 HA 2 节点） |
| `ingress_virtual_ip` | 统一入口虚拟 IP，抢占到 VIP 的节点部署 agent-gateway/registry/web-server |

`config.yaml` 随 `install` 持久化到 `~/.agentos/deploy/config.yaml`，角色推导（etcd 节点、master 节点、VIP 持有）由 `scripts/config.py` 解析。

### agent SSH 直连密钥（yuanrong 前置）

各目标主机需预生成 agent SSH 直连密钥（`up` 默认启用，脚本不生成）。默认路径 `/root/.ssh/`，已存在则无需重复创建：

```bash
ssh-keygen -t ed25519 -N '' -f /root/.ssh/agent_key
mkdir -p /root/.ssh/agent_pub
cp /root/.ssh/agent_key.pub /root/.ssh/agent_pub/authorized_keys
chmod 644 /root/.ssh/agent_pub/authorized_keys && chmod 755 /root/.ssh/agent_pub
```

**多机部署时，每台节点上都需要有一份相同的密钥**（同一套私钥 + 公钥），在任一节点生成后通过 scp 分发到其余所有节点即可。

docker-in-docker 部署时，密钥需放在 docker daemon 可见的 bind mount 路径（如挂载进容器的宿主共享目录），否则宿主路径不可见会导致挂载失败。详见下文「yuanrong」配置。

### 命令

#### 单机部署

```bash
# 1. 本机安装全部 whl 包（会把 deploy 目录持久化到 ~/.agentos/）
bash agentos.sh install

# 2. bootstrap etcd（非 etcd 节点自动跳过；自动清理历史 etcd 数据）
bash agentos.sh init

# 3. 一键部署全部组件到本机（自动前置检查 etcd 可达性）
bash agentos.sh up

# 4. 重启全部应用组件（先 down 再 up，不含 init/deinit）
bash agentos.sh restart

# 5. 停止全部应用组件（etcd 保持运行）
bash agentos.sh down

# 6. 一键查询各组件运行状态（只读，不修改系统状态）
bash agentos.sh status

# 7. 拆除 etcd（停服务 + 删 unit，保留数据）
bash agentos.sh deinit

# 8. 卸载本机全部 whl 包
bash agentos.sh uninstall
```

#### 多机部署

单机与多机部署的流程完全一致，区别仅在于 `config.yaml` 的拓扑配置不同。多机部署时，**需在各个节点上分别执行** `agentos.sh`，建议先在 master 节点执行，再在 agent 节点执行。

> **注意**：多机部署时 etcd 需全集群先就绪——所有 etcd 节点完成 `init` 后，各节点才能执行 `up`（`up` 会自动检测 etcd 可达性）。

```bash
# ---- 在每个节点上分别执行（先 master，后 agent）----

# 1. 各节点安装全部 whl 包（会把 deploy 目录持久化到 ~/.agentos/）
bash agentos.sh install

# 2. 所有 etcd 节点 bootstrap etcd（非 etcd 节点自动跳过；全集群 init 完成后再进入下一步）
bash agentos.sh init

# 3. 各节点部署全部应用组件（先 master 节点 up，再 agent 节点 up）
bash agentos.sh up

# 4. 停止全部应用组件（etcd 保持运行；先 agent 节点 down，再 master 节点 down）
bash agentos.sh down

# 5. 一键查询各组件运行状态（只读，不修改系统状态）
bash agentos.sh status

# 6. 各 etcd 节点拆除 etcd（保留数据）
bash agentos.sh deinit

# 7. 各节点卸载全部 whl 包
bash agentos.sh uninstall
```

#### etcd 数据清理（独立操作）

```bash
# 彻底删除 /var/lib/agentos/etcd 数据（默认直接清理，无交互确认）
bash etcd.sh clean
```

### 参数说明

| 参数 | 说明 |
| --- | --- |
| `install` | 在本机安装全部组件的 whl 包（不启动服务，会把 deploy 目录持久化到 `~/.agentos/`） |
| `init` | bootstrap etcd（委托 `etcd.sh clean + up`，非 etcd 节点自动跳过；自动清理历史 etcd 数据） |
| `up` | 按声明顺序部署全部应用组件（前置检查 etcd 可达，不可达则提示先 `init`） |
| `down` | 逆序停止全部应用组件（不动 etcd） |
| `status` | 一键查询各组件运行状态（只读探测，输出状态表 + 汇总计数；退出码：0=全 running/stopped，1=有 failed） |
| `deinit` | 停 etcd + 删 unit（委托 `etcd.sh down`，保留数据） |
| `uninstall` | 在本机卸载全部组件的 whl 包 |
| `restart` | 重启全部应用组件（先 down 再 up；不含 init/deinit） |
| `-h, --help` | 显示帮助信息 |

### 配置

#### config.yaml（集群拓扑）

配置文件：`deploy/config.yaml`。角色推导由 `scripts/config.py` 解析，支持 `local-ip`、`is-etcd-node`、`is-master-node`、`etcd-name`、`initial-cluster`、`etcd-advertise-ip`、`etcd-nodes`、`ingress-vip`、`all` 等子命令。

#### moosefs

配置文件：`deploy/moosefs/moosefs.conf`。主要配置项：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `MOOSEFS_MASTER_HOST` | Master 节点地址（systemd 模式下区分 master/agent 角色） | 空（systemd 模式自动取 `config.yaml` 的 `master_nodes` 第一个 IP） |
| `MOOSEFS_ENABLED` | 是否启用 MooseFS（`auto`/`yes`/`no`） | `auto`（多机自动启用，单机自动跳过） |
| `MOOSEFS_USE_SYSTEMD` | 是否使用 systemd（`auto`/`yes`/`no`） | `auto`（自动检测） |
| `MFS_MASTER_PORT` | Master 服务端口 | `9420` |
| `MFS_CHUNK_PORT` | Chunkserver 端口 | `9422` |
| `MFS_CLIENT_PORT` | Client (mfsmount) 端口 | `9421` |
| `MFS_CHUNK_DIR` | Chunkserver 数据目录 | `/data/mfschunks` |
| `MFS_MOUNT_POINT` | 共享挂载点路径 | `/home/agentos/users` |
| `MFS_GOAL` | 数据副本数 | `2`（单机自动设为 1） |

两种部署模式：
1. **systemd 模式**：各节点独立 `install` + `systemctl start`，通过 `MOOSEFS_MASTER_HOST`（或 `config.yaml` 的 `master_nodes` 第一个 IP）区分 master/agent 角色
2. **单机跳过**：其他场景（使用本地文件系统，不部署 MooseFS）

MooseFS RPM 包（moosefs-master、moosefs-chunkserver、moosefs-client）和 fuse3 依赖需由上游预装，详见 [moosefs/README.md](moosefs/README.md)。支持 openEuler 22.03-LTS-SP1/SP4 和 24.03-LTS-SP1/SP4（x86_64 和 aarch64）。

#### jiuwenbox

- 配置文件：`deploy/jiuwenbox/default-policy.yaml`（`__JIUWENSWARM_EXTENSIONS_DIR__` 在各机 start 时按该机 `pip show jiuwenswarm` 替换）
- `module.sh` 为薄封装；启停逻辑在 `jiuwenbox_deploy.sh`
- 每台机器各启动一份 jiuwenbox（无 master/agent 差异）
- 已有实例时只报错、不自动清理（对齐 yuanrong）；需先 `down` 再 `up`
- 前置：各目标机已安装 jiuwenswarm（含 `jiuwenbox-server`）

#### yuanrong

通过环境变量传入，常用变量：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `YR_PYTHON_VERSION` | Python 版本 | `3.11` |
| `YR_VERSION` | openyuanrong release 版本号 | `0.9.0` |
| `YR_PKG_BASE` | whl 包来源（远程 URL 基址或本地目录路径） | `install` 时默认指向 agentos 根目录 |
| `AGENTOS_SSH_KEY` | agent SSH 直连私钥路径（host/backend/client 三处混用） | `/root/.ssh/agent_key` |
| `AGENTOS_SSH_BACKEND_PUBLIC_DIR` | 挂进实例的公钥目录（须含 `authorized_keys`） | `/root/.ssh/agent_pub` |

详见 `yuanrong_deploy.sh -h`。

**agent SSH 直连密钥配置**：`up` 默认启用 SSH 直连（frontend bastion `:2222` + function_proxy tcp tunnel + 平台公钥挂载），不提供关闭开关（三方 agent 镜像自带 sshd，frontend→实例 sshd 段必需）。密钥由用户自行生成，部署脚本不生成；`yuanrong_deploy.sh` 启动前会校验，缺失则报错并提示。

简便模式 host/backend/client 三处用途混用同一套密钥，默认路径在 `/root/.ssh/` 下，部署前生成（**已存在则无需重复创建**）：

```bash
# 1. 生成密钥对（默认 /root/.ssh/agent_key + agent_key.pub）
ssh-keygen -t ed25519 -N '' -f /root/.ssh/agent_key

# 2. 准备公钥目录（挂进实例 /run/openyuanrong/ssh，供实例 sshd 读取）
mkdir -p /root/.ssh/agent_pub
cp /root/.ssh/agent_key.pub /root/.ssh/agent_pub/authorized_keys

# 3. 设置权限（sshd StrictModes 默认开，group/other 可写会被拒绝认证）
chmod 644 /root/.ssh/agent_pub/authorized_keys
chmod 755 /root/.ssh/agent_pub
```

权限说明：`authorized_keys` 与公钥目录不能被 group/other 可写，否则实例 sshd（以非 root 跑）的 `StrictModes` 校验失败、拒绝 backend key 认证。`0644` 文件 + `0755` 目录 + root 属主实测可用。

注意事项：

- `AGENTOS_SSH_BACKEND_PUBLIC_DIR` 不能放在 `/etc` 下（docker executor 的 `IsSafeBindSource` 黑名单含 `/etc`，会拒挂载）。默认 `/root/.ssh/agent_pub` 已避开。
- docker-in-docker 部署时，密钥需放在 docker daemon 可见的 bind mount 路径（如挂载进容器的宿主共享目录），否则宿主路径不可见会导致挂载失败。
- 生产环境建议改回三套独立密钥（host/backend/client 分开）。

#### etcd

独立脚本 `deploy/etcd.sh` 管理 etcd unit 生命周期，`agentos.sh` 的 `init`/`deinit` 委托给它。

| 子命令 | 说明 |
| --- | --- |
| `up` | 生成并启动 `agentos-etcd.service`（非 etcd 节点跳过） |
| `down` | 停止并删除 unit（保留 `/var/lib/agentos/etcd` 数据） |
| `status` | 报告 `agentos-etcd.service` 的 systemd 状态 + client 端口连通性（非 etcd 节点显示 N/A） |
| `check` | 探测 etcd 集群是否可达（TCP 连通任一 etcd_node 的 client port 即通过） |
| `clean` | 清理 etcd 数据目录（默认直接清理，无交互确认；对齐 yr start 语义） |

| 环境变量 | 说明 | 默认值 |
| --- | --- | --- |
| `YR_ETCD_CLIENT_PORT` | etcd client 端口 | `32379` |
| `YR_HEALTH_CHECK_RETRIES` | up 健康检查重试次数 | `30` |

etcd 二进制路径从 `yr config dump` 的 `values.etcd.bin_path` 探测，回退 yr 包内 `third_party/etcd/etcd`。角色推导读取 `~/.agentos/deploy/config.yaml`（由 `scripts/config.py` 解析）。

- `init` 自动 `clean + up`，无需手动清理历史数据
- `down` 保留数据，便于 `restart`；彻底清数据用 `init`（自动 clean）或独立 `./etcd.sh clean`
- `up` 前置检查 etcd 可达性（`etcd.sh check`），不可达则报错引导先 `init`

#### agent-gateway

A2X 注册中心（a2x-registry 后端 + sqlite 存储），优先 systemd 托管，无 systemd 时回退 nohup 后台进程。

| 环境变量 | 说明 | 默认值 |
| --- | --- | --- |
| `A2X_REGISTRY_PORT` | 注册中心监听端口 | `4003` |
| `A2X_REGISTRY_TLS_CERTFILE` | mTLS 服务端证书路径（三者齐全才开启） | 空（纯 http） |
| `A2X_REGISTRY_TLS_KEYFILE` | mTLS 服务端私钥路径 | 空 |
| `A2X_REGISTRY_TLS_CA_CERTS` | mTLS CA 证书路径 | 空 |
| `A2X_REGISTRY_RUN_DIR` | 运行目录（PID 文件） | `/var/run/agentos` |
| `A2X_REGISTRY_LOG_DIR` | 日志目录（nohup 模式按天新建日志） | `/var/log/agentos` |
| `A2X_REGISTRY_LOG_RETENTION_DAYS` | 日志保留天数 | `7` |
| `HEALTH_CHECK_RETRIES` | up 健康检查重试次数 | `15` |
| `STOP_WAIT_RETRIES` | down 停止等待重试次数 | `10` |

监听地址（`A2X_REGISTRY_BIND`）推导优先级：
1. `config.yaml` 的 `cluster.ingress_virtual_ip`（VIP）
2. 本机网卡 IP（`hostname -I`）
3. `127.0.0.1`

> 注意：注册中心后端禁止 `A2X_REGISTRY_BIND=0.0.0.0`，故只能绑定具体 VIP。

systemd 模式下，`install` 时会复制 `check-ingress-master.sh` 到 `/usr/local/bin/agentos-check-ingress-master`，作为 unit 的 `ExecStartPre`：本机未持有 `ingress_virtual_ip` 时阻止服务启动（fail-closed）。`up` 钩子只做幂等启动，不做 master 判定。

whl 包来源：`install` 时从 agentos 根目录匹配 `a2x_registry-*-py3-none-any.whl`。

#### jiuwenswarm

配置文件：`deploy/jiuwenswarm/.env.custom`（基于 submodule 中的 `.env.example` 修改）。主要配置项：

| 变量 | 说明 |
| --- | --- |
| `CLUSTER_HOSTS` | 目标主机 IP 列表 |
| `JIUWENSWARM_PACKAGE_URL` | jiuwenswarm 安装包 URL（up 时若远程主机未安装 jiuwenswarm 则用此 URL pip 安装） |
| `MODEL_PROVIDER` / `MODEL_NAME` / `API_BASE` / `API_KEY` | 大模型接口配置 |
| `EMBED_MODEL` / `EMBED_API_BASE` / `EMBED_API_KEY` | 向量模型接口配置 |
| `GATEWAY_HOST` / `GATEWAY_PORT` | gateway 进程监听地址/端口（host 留空时自动绑定 `config.yaml` 的 `ingress_virtual_ip`） |
| `WEB_PORT` / `WEB_ENABLED` | web 前端端口/是否随 `up` 启动 |
| `WEB_STATIC_PORT` | web 前端静态资源服务端口 |
| `SANDBOX_TYPE` / `TOOL_SANDBOX_*` | 沙箱类型与工具沙箱配置 |

> **工具沙箱镜像需手动拉取**：`install` 和 `up` 均**不会**自动拉取 `TOOL_SANDBOX_IMAGE` 指定的镜像。当 `TOOL_SANDBOX_ENABLE=true` 时，`install` 会打印提示，但用户需自行在目标主机上执行 `docker pull` 拉取镜像，否则 jiuwen agent 工具沙箱功能不可用。

```bash
# 拉取工具沙箱镜像（镜像地址对应 .env.custom 中的 TOOL_SANDBOX_IMAGE）
docker pull swr.cn-southwest-2.myhuaweicloud.com/yuanrong-dev/yr-runtime-sandbox:latest
```

若目标主机无法访问华为云 SWR 镜像仓库，可在有网络的机器上拉取后通过 `docker save` / `docker load` 离线导入：

```bash
# 在有网络的机器上导出
docker save -o yr-runtime-sandbox.tar swr.cn-southwest-2.myhuaweicloud.com/yuanrong-dev/yr-runtime-sandbox:latest

# 传输到目标主机后导入
docker load -i yr-runtime-sandbox.tar
```

#### whl 包来源

`install` 时统一从 agentos 根目录（`deploy` 的同级目录）获取 whl 包：

- **openyuanrong**：`YR_PKG_BASE` 默认指向 agentos 根目录，yuanrong 脚本按版本/arch 自动拼接 whl 文件名
- **jiuwenswarm**：匹配 `jiuwenswarm-*-py3-none-any.whl`（如 `jiuwenswarm-0.2.3-py3-none-any.whl`，已包含 gateway）
- **a2x-registry**：匹配 `a2x_registry-*-py3-none-any.whl`（agent-gateway 模块）
- **moosefs**：从 agentos 根目录获取 RPM 包（moosefs-master/chunkserver/client）

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
    # 调用你的部署脚本，调度器透传额外参数
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

# 只读状态探测（可选；输出格式: mymodule|<service>|<state>|<detail>）
mymodule_status() {
    # state ∈ running / stopped / failed / disabled / N/A
    echo "mymodule|mymodule.service|running|active"
}
```

### 第 2 步：注册到 `MODULES` 数组

编辑 `agentos.sh` 顶部的 `MODULES` 数组，按部署顺序添加模块名：

```bash
MODULES=("moosefs" "jiuwenbox" "yuanrong" "agent-gateway" "jiuwenswarm" "mymodule")
```

### 完成

此后 `bash agentos.sh up` 会自动按声明顺序部署，`bash agentos.sh down` 会逆序卸载，`install` / `uninstall` 同理。

### 钩子函数说明

| 钩子 | 调用时机 | 参数 | 典型实现 |
| --- | --- | --- | --- |
| `<module>_up` | `up` / `restart` 时，按声明顺序调用 | 透传额外参数 | 调用模块部署脚本启动服务 |
| `<module>_down` | `down` / `restart` 时，逆序调用 | 透传额外参数 | 调用模块部署脚本停止服务 |
| `<module>_install` | `install` 时，按声明顺序调用 | 透传额外参数（通常 install 不需要） | 本机 pip 安装 whl 包 |
| `<module>_uninstall` | `uninstall` 时，逆序调用 | 透传额外参数（通常 uninstall 不需要） | 本机 pip 卸载 whl 包 |
| `<module>_status` | `status` 时，按声明顺序调用 | 无 | 只读探测本组件运行状态，输出 `Component\|Service\|State\|Detail` 行 |

### 可用的全局变量

`module.sh` 中可直接引用以下变量（由 `agentos.sh` 在 `source` 前定义）：

| 变量 | 说明 |
| --- | --- |
| `SCRIPT_DIR` | `deploy/` 目录的绝对路径 |
| `AGENTOS_ROOT` | agentos 根目录（`deploy` 的同级目录）的绝对路径 |
| `MODULES` | 已注册模块数组 |
| `YR_PYTHON_VERSION` | Python 版本（默认 `3.11`） |
| `CLUSTER_HOSTS` | 主机列表 |
| `AGENTOS_SSH_KEY` | agent SSH 直连私钥路径（默认 `/root/.ssh/agent_key`） |
| `AGENTOS_SSH_BACKEND_PUBLIC_DIR` | agent SSH 公钥目录（默认 `/root/.ssh/agent_pub`） |
| `info` / `success` / `warning` / `error` | 日志函数 |

### 可选钩子

钩子函数是可选的。若某模块未实现某个钩子（如纯部署型模块不需要 `install`），调度引擎会打印 warning 并跳过，不会报错中断。

> **`status` 钩子例外**：`status` 命令不复用 `run_hooks`（需占位而非跳过）。若模块未实现 `_status` 钩子，状态表会为该组件占位一行显示 "not supported"，继续探测其余组件。

### 命名规范

- 模块名使用小写字母 + 数字 + 连字符（如 `mymodule`、`agent-gateway`、`skill-store`）
- 钩子函数名必须为 `<module名>_<hook>`，其中 `<hook>` 为 `up` / `down` / `install` / `uninstall` / `status`
- `module.sh` 中定义的内部函数建议加 `_` 前缀（如 `_mymodule_helper`）避免命名冲突
