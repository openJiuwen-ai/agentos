# 一体机 Compose 部署与验证指南

六个容器：**Frontend** + **image-process** + **PostgreSQL 18** + **LiteLLM** + **VictoriaMetrics** + **Grafana**。

## 服务与端口

宿主机端口在 `.env` 中配置（示例见 `.env.example`），compose 不设默认值。

| 服务 | 镜像 | 环境变量 | 默认端口 | 说明 |
|------|------|----------|----------|------|
| `frontend` | `agentos-control-panel` | `FRONTEND_PORT` | 8090 | CI 构建；Nginx 托管 Vue 静态页 |
| `image-process` | `agentos-image-process` | -- | （不对宿主暴露） | Agent 镜像构建；仅 `image-build` 内网 |
| `postgres` | `postgres:18.0` | `POSTGRES_PORT` | 5432 | LiteLLM 数据库 |
| `litellm` | `ghcr.io/berriai/litellm-database:v1.91.1` | `LITELLM_PORT` | 8100 | 推理代理 |
| `victoriametrics` | `victoriametrics/victoria-metrics:v1.135.0` | `VICTORIAMETRICS_PORT` | 8428 | 指标存储 |
| `grafana` | `grafana/grafana:12.4.2` | `GRAFANA_PORT` | 8093 | 监控面板 |

**宿主机原生服务（非容器）：**

| 服务 | 二进制安装路径 | 默认端口 | 说明 |
|------|---------------|----------|------|
| `node_exporter` | `/usr/bin/node_exporter` | 8091 | 主机指标采集（systemd） |
| `npu-exporter` | `/usr/local/bin/npu-exporter` | 8092 | NPU 指标采集（systemd timer） |

## 前置条件

| 项 | 说明 |
| ---- | ---- |
| Docker | 已安装 Docker Engine + Compose 插件 |
| 端口 | `.env` 中宿主机端口已配置且未被占用 |
| 环境变量 | `deploy.sh install` 自动从 `.env.example` 生成 `.env`，支持交互/非交互模式 |
| 前端镜像 | CI 已构建并推送到仓库，或通过 `docker load` 导入本机 |
| image-process 镜像 | `docker compose build image-process`（或预先 `docker build -t agentos-image-process ../image_process`） |
| agent-base | 宿主机需已有 `agent-base:1.0`（制品需手动准备） |
| systemd | 宿主机使用 systemd init（Ubuntu / Debian / CentOS 等） |

### 所需版本清单

| 类型 | 名称 | 版本 |
|------|------|------|
| 容器镜像 | `postgres` | `18.0` |
| 容器镜像 | `ghcr.io/berriai/litellm-database` | `v1.91.1` |
| 容器镜像 | `victoriametrics/victoria-metrics` | `v1.135.0` |
| 容器镜像 | `grafana/grafana` | `12.4.2` |
| 二进制文件 | `node_exporter` | `v1.12.1` |
| 二进制文件 | `npu-exporter` | `>26.0.0` |

### 环境变量配置要求

`deploy.sh install` 非交互模式下，以下环境变量可提前设置以覆盖默认值：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `POSTGRES_USER` | `agentos` | PostgreSQL 用户名 |
| `POSTGRES_PASSWORD` | `agentos123` | PostgreSQL 密码 |
| `AGENTOS_ADMIN_USERNAME` | `admin` | 管理后台用户名 |
| `AGENTOS_ADMIN_PASSWORD` | `admin123` | 管理后台密码 |
| `LITELLM_HOST` | 自动检测本机 IP | LiteLLM 监听地址 |
| `NODE_EXPORTER_HOST` | 自动检测本机 IP | node_exporter 监听地址 |
| `NPU_EXPORTER_HOST` | 自动检测本机 IP | npu_exporter 监听地址 |
| `AGENT_REGISTER_URL` | `http://<本机IP>:4003` | 注册中心地址 |

> 以下密钥由安装脚本自动生成，**无需手动设置**：
> - `AGENTOS_JWT_SECRET_KEY` — JWT 签名密钥
> - `LITELLM_MASTER_KEY` — LiteLLM 管理密钥（sk- 前缀）
> - `LITELLM_KEY_ENCRYPTION_KEY` — LiteLLM 密钥加密密钥

### 镜像准备

**打包运行镜像**

```bash
cd control-panel
docker build -f image/Dockerfile -t agentos-control-panel .
```

**拉取公共镜像**

若目标环境没有外网，则从有网环境拉取公共镜像，再打包传到无网环境。

```bash
docker pull postgres:18.0
docker pull ghcr.io/berriai/litellm-database:v1.91.1
docker pull victoriametrics/victoria-metrics:v1.135.0
docker pull grafana/grafana:12.4.2

docker save -o postgres_18.0.tar postgres:18.0
docker save -o litellm-database_v1.91.1.tar ghcr.io/berriai/litellm-database:v1.91.1
docker save -o victoria-metrics_v1.135.0.tar victoriametrics/victoria-metrics:v1.135.0
docker save -o grafana_12.4.2.tar grafana/grafana:12.4.2

# 目标机：
docker load -i postgres_18.0.tar
docker load -i litellm-database_v1.91.1.tar
docker load -i victoria-metrics_v1.135.0.tar
docker load -i grafana_12.4.2.tar

docker images | grep -E 'agentos|postgres|litellm|victoria-metrics|grafana'
```

**image-process / agent-base（构建机准备，部署机拉取或 load）**

```bash
cd control-panel
docker build -t agentos-image-process:latest image_process
docker build -f image_process/base.Dockerfile -t agent-base:1.0 image_process

docker save -o agentos-image-process_latest.tar agentos-image-process:latest
docker save -o agent-base_1.0.tar agent-base:1.0

# 目标机：
docker load -i agentos-image-process_latest.tar
docker load -i agent-base_1.0.tar
```

### Exporter 准备

Exporter 运行在宿主机（非容器），提供指标采集。`deploy.sh install` 会自动拷贝二进制并注册 systemd 服务。

需要准备的 exporter 及指定版本：

| Exporter | 版本 | 来源 |
|----------|------|------|
| `node_exporter` | v1.12.1 | [GitHub Releases](https://github.com/prometheus/node_exporter/releases/tag/v1.12.1) |
| `npu-exporter` | >26.0.0 | [MindCluster Releases](https://gitcode.com/Ascend/mind-cluster/releases/v26.0.0) |

**node_exporter**

从 [GitHub Releases](https://github.com/prometheus/node_exporter/releases/tag/v1.12.1) 下载对应机器架构的压缩包（如 `linux-amd64`、`linux-arm64` 等），解压后将 `node_exporter` 二进制放入 `deploy/node-exporter/` 目录。

```bash
# 示例（以 linux-amd64 为例，实际根据架构选择）：
# amd64 架构：
wget https://github.com/prometheus/node_exporter/releases/download/v1.12.1/node_exporter-1.12.1.linux-amd64.tar.gz
tar xzf node_exporter-1.12.1.linux-amd64.tar.gz
cp node_exporter-1.12.1.linux-amd64/node_exporter deploy/node-exporter/

# arm64 架构：
wget https://github.com/prometheus/node_exporter/releases/download/v1.12.1/node_exporter-1.12.1.linux-arm64.tar.gz
tar xzf node_exporter-1.12.1.linux-arm64.tar.gz
cp node_exporter-1.12.1.linux-arm64/node_exporter deploy/node-exporter/
```

要求：`deploy/node-exporter/node_exporter` 文件存在，且 `deploy/node-exporter/node_exporter.service` 文件存在（已随仓库提供）。

> **注意**：下载时请根据目标机器的 CPU 架构选择对应的软件包，可通过 `uname -m` 查看本机架构。

**npu-exporter**

从 [MindCluster Releases](https://gitcode.com/Ascend/mind-cluster/releases/v26.1.0) 下载对应机器架构的压缩包，解压后将以下文件放入 `deploy/npu-exporter/` 目录：

| 文件 | 必需 | 说明 |
|------|------|------|
| `npu-exporter` | 是 | 二进制文件 |
| `npu-exporter.service` | 是 | systemd service unit |
| `npu-exporter.timer` | 是 | systemd timer unit |
| `metricConfiguration.json` | 否 | 指标配置（安装时拷贝到 `/usr/local/`） |
| `pluginConfiguration.json` | 否 | 插件配置（安装时拷贝到 `/usr/local/`） |

```bash
# 示例（根据实际包名调整）：
# x86_64 架构：
unzip Ascend-mindxd1-npu-exporter_<version>_linux-x86_64.zip -d deploy/npu-exporter/
# aarch64 架构：
unzip Ascend-mindxd1-npu-exporter_<version>_linux-aarch64.zip -d deploy/npu-exporter/
```

> **注意**：下载时请根据目标机器的 CPU 架构选择对应的软件包（如 `linux-x86_64`、`linux-aarch64`），可通过 `uname -m` 查看本机架构。

---

## 部署流程

### 快速部署（一键脚本）

```bash
# 1. 安装（非交互式，自动拷贝到 ~/.agentos/.agent-manager）：
sudo bash deploy.sh install

# 2. 进入安装目录（后续所有操作在此目录执行）：
cd ~/.agentos/.agent-manager

# 3. 启动服务：
sudo bash deploy.sh up

# 4. 查看状态：
sudo bash deploy.sh status
```

交互式安装（逐项询问密码、IP 等配置）：

```bash
sudo bash deploy.sh install -i
cd ~/.agentos/.agent-manager
sudo bash deploy.sh up
```

**所有命令：**

| 命令 | 说明 |
|------|------|
| `deploy.sh install` | 安装：.env 初始化 + exporter 注册 + 镜像拉取 |
| `deploy.sh install -i` | 交互式安装（逐项询问配置） |
| `deploy.sh uninstall` | 卸载：停止服务 + 注销 systemd（保留数据和 .env） |
| `deploy.sh uninstall --clean` | 卸载：删除数据卷和 .env |
| `deploy.sh up` | 启动：更新 exporter 配置 → 启动服务 |
| `deploy.sh down` | 停止：docker compose → node/npu_exporter（反序） |
| `deploy.sh restart` | 重启：down → up |
| `deploy.sh status` | 查看服务状态（含端口健康检查） |

---

> **强烈不建议**：以下分步部署流程仅用于特殊场景（如调试、定制化部署）。正常部署请使用上方的一键脚本。

### 分步部署（特殊场景，不优先使用）

#### 1. 准备镜像

**打包运行镜像**

```bash
cd control-panel
docker build -f image/Dockerfile -t agentos-control-panel .
```

**拉取公共镜像**

```bash
docker pull postgres:18.0
docker pull ghcr.io/berriai/litellm-database:v1.91.1
docker pull victoriametrics/victoria-metrics:v1.135.0
docker pull grafana/grafana:12.4.2

docker save -o postgres_18.0.tar postgres:18.0
docker save -o litellm-database_v1.91.1.tar ghcr.io/berriai/litellm-database:v1.91.1
docker save -o victoria-metrics_v1.135.0.tar victoriametrics/victoria-metrics:v1.135.0
docker save -o grafana_12.4.2.tar grafana/grafana:12.4.2

# 目标机：
docker load -i postgres_18.0.tar
docker load -i litellm-database_v1.91.1.tar
docker load -i victoria-metrics_v1.135.0.tar
docker load -i grafana_12.4.2.tar
```

#### 2. 部署 node_exporter（宿主机）

node_exporter 运行在宿主机（非容器），提供 CPU / 内存 / 磁盘 / 网络等指标。

前置条件：将解压后的 `node_exporter` 二进制放入 `deploy/node-exporter/` 目录，`deploy.sh install` 会自动拷贝到 `/usr/bin` 并注册 systemd 服务。

```bash
systemctl status node_exporter
curl -s http://127.0.0.1:8091/metrics | head -5
```

#### 3. 拉起docker compose

```bash
cd control-panel/deploy

cp .env.example .env
# 编辑 .env：POSTGRES_PASSWORD、LITELLM_MASTER_KEY（须以 sk- 开头）

docker compose pull
docker compose up -d
```

**检查状态**

```bash
docker compose ps

curl -I http://127.0.0.1:8090/
docker ps --filter name=deploy-postgres-1
curl http://127.0.0.1:8100/health/liveliness
curl http://127.0.0.1:8428/health
curl http://127.0.0.1:8093/api/health
```

**停止与清理**

```bash
docker compose down
docker compose down -v  # 清空指标数据
```
